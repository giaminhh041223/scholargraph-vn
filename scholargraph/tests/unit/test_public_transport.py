"""Mock HTTP evidence only; verified fixture policy is synthetic."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime,timezone
import httpx
import pytest
from scholargraph.public_search.contracts import PublicSearchConfig,load_config
from scholargraph.public_search.transport import Transport,TransportError,RateState
ROOT=Path(__file__).resolve().parents[2]

class Clock:
    def __init__(self): self.now=0.; self.waits=[]
    def __call__(self): return self.now
    def sleep(self,value): self.waits.append(value); self.now+=value

def config(**changes):
    row=json.loads((ROOT/"configs/public_search.json").read_text())
    for p in row["sources"].values():
        p.update(source_policy_verified=True,policy_evidence_sha256="b"*64)
        p.update(changes)
    return PublicSearchConfig.model_validate(row)

def transport(handler,cfg=None):
    clock=Clock()
    client=httpx.Client(transport=httpx.MockTransport(handler))
    return Transport(config() if cfg is None else cfg,client=client,clock=clock,sleeper=clock.sleep,
                     wall_clock=lambda:datetime(2026,9,30,tzinfo=timezone.utc),environ={}),clock

def test_encoding_hash_and_body():
    seen=[]
    def handler(req):
        seen.append(req)
        return httpx.Response(200,json={"synthetic":True,"results":[]})
    t,c=transport(handler)
    r=t.get("openalex",{"search":"graph & C++ / ViÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¡t"},deadline=t.deadline())
    assert seen[0].url.params["search"]=="graph & C++ / ViÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¡t"
    assert json.loads(r.body)["synthetic"] is True and len(r.sha256)==64 and r.attempts==1
    t.get("openalex",{},deadline=t.deadline()); assert c.waits==[1.0]

def test_policy_and_auth_fail_before_network():
    def forbidden(_): pytest.fail("network must not be called")
    t,_=transport(forbidden,config(source_policy_verified=False,policy_evidence_sha256=None))
    with pytest.raises(TransportError,match="not verified"): t.get("arxiv",{},deadline=30.)
    t,_=transport(forbidden,config(auth_mode="bearer",key_env="SYNTHETIC_KEY"))
    with pytest.raises(TransportError,match="credential missing"): t.get("openalex",{},deadline=30.)

@pytest.mark.parametrize("status",[401,403])
def test_auth_no_retry_no_secret(status):
    seen=[]
    def handler(req): seen.append(req); return httpx.Response(status,text="synthetic-secret")
    t,c=transport(handler,config(auth_mode="bearer",key_env="SYNTHETIC_KEY")); t.environ={"SYNTHETIC_KEY":"synthetic-secret"}
    with pytest.raises(TransportError) as exc: t.get("openalex",{},deadline=30.)
    assert exc.value.error.kind=="auth" and len(seen)==1 and c.waits==[]
    assert "synthetic-secret" not in str(exc.value) and "synthetic-secret" not in str(seen[0].url)
    assert seen[0].headers["authorization"]=="Bearer synthetic-secret"

@pytest.mark.parametrize("delay",["31","Wed, 30 Sep 2026 00:01:00 GMT"])
def test_quota_wait_not_shortened(delay):
    seen=[]
    def handler(req): seen.append(req); return httpx.Response(429,headers={"Retry-After":delay})
    t,c=transport(handler)
    with pytest.raises(TransportError) as exc: t.get("openalex",{},deadline=30.)
    assert exc.value.error.kind=="quota" and len(seen)==1 and c.waits==[]
    assert exc.value.error.retry_after_seconds>=31

def test_retry_after_then_success():
    seen=[]
    def handler(req):
        seen.append(req)
        return httpx.Response(429,headers={"Retry-After":"3"}) if len(seen)==1 else httpx.Response(200,json={"synthetic":True})
    t,c=transport(handler)
    assert t.get("openalex",{},deadline=30.).attempts==2
    assert c.waits==[3.]

@pytest.mark.parametrize("headers",[{"retry-after":"-1"},{"retry-after":"NaN"},{"retry-after":"1.5"},[("Retry-After","1"),("Retry-After","2")]])
def test_malformed_retry_header(headers):
    t,_=transport(lambda _:httpx.Response(429,headers=headers))
    with pytest.raises(TransportError) as exc: t.get("openalex",{},deadline=30.)
    assert exc.value.error.kind=="schema"

@pytest.mark.parametrize("response",[
    httpx.Response(200,content=b"{}"),
    httpx.Response(200,headers={"content-type":"text/html"},content=b"{}"),
    httpx.Response(200,headers={"content-type":"application/json","content-length":"invalid"},content=b"{}"),
    httpx.Response(200,headers={"content-type":"application/json"},content=b""),
    httpx.Response(200,headers={"content-type":"application/json"},content=b"123456789"),
    httpx.Response(200,headers=[("content-type","application/json"),("content-type","application/json")],content=b"{}"),
])
def test_malformed_or_oversized_payload(response):
    t,_=transport(lambda _:response,config(max_body_bytes=8))
    with pytest.raises(TransportError) as exc: t.get("openalex",{},deadline=30.)
    assert exc.value.error.kind=="schema"

def test_timeout_bounded_redacted():
    seen=[]
    def handler(req): seen.append(req); raise httpx.ReadTimeout("synthetic-secret-URL",request=req)
    t,c=transport(handler)
    with pytest.raises(TransportError) as exc: t.get("openalex",{},deadline=30.)
    assert exc.value.error.kind=="timeout" and len(seen)==3
    assert "secret" not in str(exc.value) and c.waits==[1.,2.]

def test_redirect_no_follow():
    seen=[]
    def handler(req): seen.append(req); return httpx.Response(302,headers={"location":"http://127.0.0.1/private"})
    t,_=transport(handler)
    with pytest.raises(TransportError): t.get("openalex",{},deadline=30.)
    assert len(seen)==1

def test_secret_params_and_expired_deadline():
    t,_=transport(lambda _:pytest.fail("no network"))
    for params in [{"api_key":"synthetic-secret"},{"query":True}]:
        with pytest.raises(TransportError): t.get("openalex",params,deadline=30.)
    with pytest.raises(TransportError): t.get("openalex",{},deadline=0.)
    with pytest.raises(TransportError): t.get("openalex",{},deadline=float("nan"))

def test_concurrent_source_serialization():
    # Real monotonic clock for lock contention; mock network only.
    import threading,time
    state={"active":0,"peak":0}; lock=threading.Lock()
    def handler(_):
        with lock:
            state["active"]+=1; state["peak"]=max(state["peak"],state["active"])
        time.sleep(.01)
        with lock: state["active"]-=1
        return httpx.Response(200,json={"synthetic":True})
    client=httpx.Client(transport=httpx.MockTransport(handler))
    t=Transport(config(interval_seconds=0.),client=client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(t.get,"openalex",{},deadline=t.deadline()) for _ in range(2)]
        assert all(f.result().attempts==1 for f in futures)
    assert state["peak"]==1


def test_quota_cooldown_survives_failed_request():
    seen=[]
    def handler(req):
        seen.append(req)
        return httpx.Response(429,headers={"retry-after":"60"})
    t,c=transport(handler)
    with pytest.raises(TransportError): t.get("openalex",{},deadline=30.)
    with pytest.raises(TransportError): t.get("openalex",{},deadline=30.)
    assert len(seen)==1 and c.waits==[]


def test_stream_body_cap_without_content_length():
    class Payload(httpx.SyncByteStream):
        def __iter__(self): yield b"12345"; yield b"67890"
    t,_=transport(lambda _:httpx.Response(200,headers={"content-type":"application/json"},stream=Payload()),config(max_body_bytes=8))
    with pytest.raises(TransportError,match="byte cap"): t.get("openalex",{},deadline=30.)


def test_fixed_deadline_and_cross_request_rate_state():
    c=Clock(); state=RateState(); seen=[]
    def handler(req): seen.append(req); return httpx.Response(200,headers={"content-type":"application/atom+xml"},content=b"<feed/>")
    client=httpx.Client(transport=httpx.MockTransport(handler))
    first=Transport(config(),client=client,clock=c,sleeper=c.sleep,rate_state=state)
    assert first.deadline()==30.
    first.get("arxiv",{},deadline=first.deadline())
    second=Transport(config(),client=client,clock=c,sleeper=c.sleep,rate_state=state)
    second.get("arxiv",{},deadline=second.deadline())
    assert c.waits==[3.] and first.deadline()==30.
