[CmdletBinding()]
param()

# Read-only continuity validator. Run from any working directory.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$workspaceRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot '..'))
$issues = New-Object 'System.Collections.Generic.List[string]'
$warnings = New-Object 'System.Collections.Generic.List[string]'

function Add-Issue([string]$message) {
    $issues.Add($message)
}
function Read-ProjectJson([string]$relativePath) {
    $fullPath = Join-Path $projectRoot $relativePath
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        throw "Missing JSON file: $relativePath"
    }
    return (Get-Content -LiteralPath $fullPath -Raw -Encoding UTF8 | ConvertFrom-Json)
}
function Check-Artifact([string]$relativePath, [string]$context) {
    if ([string]::IsNullOrWhiteSpace($relativePath)) {
        Add-Issue "$context has an empty artifact path"
        return
    }
    if ([IO.Path]::IsPathRooted($relativePath)) {
        Add-Issue "$context must use a project-relative path: $relativePath"
        return
    }
    $fullPath = [IO.Path]::GetFullPath((Join-Path $projectRoot $relativePath))
    $prefix = $projectRoot.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if (-not $fullPath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        Add-Issue "$context escapes project root: $relativePath"
        return
    }
    if (-not (Test-Path -LiteralPath $fullPath)) {
        Add-Issue "$context missing artifact: $relativePath"
    }
}
try {
    $board = Read-ProjectJson 'management/tasks.json'
    $state = Read-ProjectJson 'management/state.json'
    $routing = Read-ProjectJson 'management/model_routing.json'
    $chats = Read-ProjectJson 'management/chat_registry.json'
    $modelMatrix = Get-Content -LiteralPath (Join-Path $projectRoot 'docs/TASK_MODEL_MATRIX.md') -Raw -Encoding UTF8
    $taskSpec = Get-Content -LiteralPath (Join-Path $projectRoot 'docs/TASKS.md') -Raw -Encoding UTF8
    $handoff = Get-Content -LiteralPath (Join-Path $projectRoot $state.handoff_path) -Raw -Encoding UTF8
} catch {
    Write-Output "FAIL: $($_.Exception.Message)"
    exit 1
}

$statuses = @('TODO', 'IN_PROGRESS', 'REVIEW', 'DONE', 'BLOCKED', 'DEFERRED')
$taskById = @{}
foreach ($task in $board.tasks) {
    if ($task.id -notmatch '^SG-\d{3}$') { Add-Issue "Invalid task ID: $($task.id)" }
    if ($taskById.ContainsKey($task.id)) { Add-Issue "Duplicate task: $($task.id)" }
    $taskById[$task.id] = $task
    if ($statuses -notcontains $task.status) { Add-Issue "Invalid status for $($task.id)" }
    if ($task.priority -notin @('CORE', 'STRETCH')) { Add-Issue "Invalid priority for $($task.id)" }
    if ($task.estimate_human_hours -lt 0) { Add-Issue "Negative estimate for $($task.id)" }
    $headingPattern = '(?m)^## ' + [regex]::Escape($task.id) + ' '
    if ([regex]::Matches($taskSpec, $headingPattern).Count -ne 1) {
        Add-Issue "$($task.id) must have exactly one task card"
    }
    if ($task.status -in @('IN_PROGRESS', 'REVIEW', 'DONE')) {
        if ([string]::IsNullOrWhiteSpace($task.owner)) { Add-Issue "$($task.id) requires owner" }
        if ([string]::IsNullOrWhiteSpace($task.session_id)) {
            Add-Issue "$($task.id) requires session ID"
        } else {
            Check-Artifact "management/logs/$($task.session_id).md" "$($task.id) session"
        }
    }
    if ($task.status -eq 'BLOCKED' -and [string]::IsNullOrWhiteSpace($task.blocked_reason)) {
        Add-Issue "$($task.id) BLOCKED requires a reason"
    }
    if ($task.status -eq 'DONE') {
        if (@($task.evidence).Count -eq 0) { Add-Issue "$($task.id) DONE needs evidence" }
        if (@($task.verification).Count -eq 0) { Add-Issue "$($task.id) DONE needs verification" }
        foreach ($artifact in $task.evidence) { Check-Artifact $artifact "$($task.id) evidence" }
        foreach ($check in $task.verification) {
            if ([string]::IsNullOrWhiteSpace($check)) { Add-Issue "$($task.id) has empty verification" }
        }
    }
}
# Detect task cards missing from the registry as well as stale IDs.
foreach ($card in [regex]::Matches($taskSpec, '(?m)^## (SG-\d{3}) ')) {
    if (-not $taskById.ContainsKey($card.Groups[1].Value)) {
        Add-Issue "Task card is not registered: $($card.Groups[1].Value)"
    }
}
foreach ($task in $board.tasks) {
    $seenDeps = @{}
    foreach ($dep in $task.dependencies) {
        if ($seenDeps.ContainsKey($dep)) { Add-Issue "$($task.id) duplicate dependency $dep" }
        $seenDeps[$dep] = $true
        if (-not $taskById.ContainsKey($dep)) {
            Add-Issue "$($task.id) unknown dependency $dep"
            continue
        }
        if ($dep -eq $task.id) { Add-Issue "$($task.id) depends on itself" }
        if ($task.status -in @('IN_PROGRESS', 'REVIEW', 'DONE') -and $taskById[$dep].status -ne 'DONE') {
            Add-Issue "$($task.id) started/completed before dependency $dep is DONE"
        }
    }
}
$visited = @{}
$visiting = @{}
function Visit-Task([string]$taskId) {
    if ($visited.ContainsKey($taskId)) { return }
    if ($visiting.ContainsKey($taskId)) { Add-Issue "Dependency cycle at $taskId"; return }
    if (-not $taskById.ContainsKey($taskId)) { return }
    $visiting[$taskId] = $true
    foreach ($dep in $taskById[$taskId].dependencies) { Visit-Task $dep }
    $visiting.Remove($taskId)
    $visited[$taskId] = $true
}
foreach ($task in $board.tasks) { Visit-Task $task.id }

# Recommendations are project data, not executable app model settings.
$supportedModels = @('gpt-6-astra', 'gpt-5.6-sol', 'gpt-5.6-terra', 'gpt-5.6-luna', 'gpt-5.5')
$profileById = @{}
foreach ($property in $routing.profiles.PSObject.Properties) {
    $profileById[$property.Name] = $property.Value
    if ($supportedModels -notcontains $property.Value.model) { Add-Issue "Unknown routing model: $($property.Value.model)" }
    if ($property.Value.reasoning -notin @('low', 'medium', 'high', 'xhigh', 'max', 'ultra')) {
        Add-Issue "Unsupported reasoning in $($property.Name)"
    }
    if ($property.Value.model -in @('gpt-5.6-luna', 'gpt-5.5') -and $property.Value.reasoning -eq 'ultra') {
        Add-Issue "Reasoning ultra unavailable for $($property.Value.model) in verified host catalog"
    }
}
if ($routing.mode -ne 'advisory_not_runtime_configuration') { Add-Issue 'Routing must remain advisory' }
Check-Artifact $routing.task_registry_path 'routing.task_registry_path'
Check-Artifact $routing.chat_registry_path 'routing.chat_registry_path'
$laneById = @{}
foreach ($lane in $chats.lanes) {
    if ($laneById.ContainsKey($lane.chat_id)) { Add-Issue "Duplicate lane: $($lane.chat_id)" }
    $laneById[$lane.chat_id] = $lane
    if (-not $profileById.ContainsKey($lane.default_profile)) { Add-Issue "Unknown profile for lane $($lane.chat_id)" }
}
if (-not $laneById.ContainsKey($chats.single_writer_coordinator)) { Add-Issue 'Coordinator lane does not exist' }
if (-not $laneById.ContainsKey($routing.defaults.review_chat_id)) { Add-Issue 'Review lane does not exist' }
$routeById = @{}
$modelNames = @{'gpt-6-astra'='Astra'; 'gpt-5.6-sol'='Sol'; 'gpt-5.6-terra'='Terra'; 'gpt-5.6-luna'='Luna'; 'gpt-5.5'='GPT-5.5'}
foreach ($route in $routing.tasks) {
    if ($routeById.ContainsKey($route.task_id)) { Add-Issue "Duplicate route: $($route.task_id)" }
    $routeById[$route.task_id] = $route
    if (-not $taskById.ContainsKey($route.task_id)) { Add-Issue "Unknown task in routing: $($route.task_id)" }
    foreach ($profileId in @($route.primary_profile, $route.review_profile)) {
        if (-not $profileById.ContainsKey($profileId)) { Add-Issue "Unknown profile $profileId for $($route.task_id)" }
    }
    if ($routing.assistant_only_profiles -contains $route.primary_profile) { Add-Issue "Assistant-only profile cannot lead $($route.task_id)" }
    if (-not $laneById.ContainsKey($route.chat_id)) { Add-Issue "Unknown lane for $($route.task_id)" }
    if ($route.review_mode -notin @('self_check_allowed', 'fresh_context_required')) { Add-Issue "Invalid review mode for $($route.task_id)" }
    if ($route.human_approval_required -isnot [bool]) { Add-Issue "Human gate must be boolean for $($route.task_id)" }
    if ([string]::IsNullOrWhiteSpace($route.rationale)) { Add-Issue "Missing routing rationale for $($route.task_id)" }
    $matrixRows = @($modelMatrix -split '\r?\n' | Where-Object { $_ -match ('^\| \[' + [regex]::Escape($route.task_id) + '\]') })
    if ($matrixRows.Count -ne 1) {
        Add-Issue "Expected one matrix row for $($route.task_id)"
    } elseif ($profileById.ContainsKey($route.primary_profile) -and $profileById.ContainsKey($route.review_profile)) {
        $cells = $matrixRows[0] -split '\|'
        if ($cells.Count -ne 9) {
            Add-Issue "Invalid matrix columns for $($route.task_id)"
        } else {
            $primary = $profileById[$route.primary_profile]
            $review = $profileById[$route.review_profile]
            $expectedPrimary = "$($modelNames[$primary.model]) · $($primary.reasoning)"
            $expectedReview = "$($modelNames[$review.model]) · $($review.reasoning)"
            $expectedMode = if ($route.review_mode -eq 'fresh_context_required') { 'Review riêng' } else { 'Tự kiểm được' }
            $expectedHuman = if ($route.human_approval_required) { 'Bắt buộc' } else { 'Theo checkpoint' }
            if ($cells[2].Trim() -ine $expectedPrimary -or $cells[3].Trim() -cne $route.chat_id -or
                $cells[4].Trim() -ine $expectedReview -or $cells[5].Trim() -cne $expectedMode -or
                $cells[6].Trim() -cne $expectedHuman -or $cells[7].Trim() -cne $route.rationale) {
                Add-Issue "Model matrix disagrees with routing for $($route.task_id)"
            }
        }
    }
}
foreach ($task in $board.tasks) {
    if (-not $routeById.ContainsKey($task.id)) { Add-Issue "Missing model route for $($task.id)" }
}
if ([regex]::Matches($modelMatrix, '(?m)^\| \[SG-\d{3}\]').Count -ne $board.tasks.Count) { Add-Issue 'Matrix row count disagrees with task registry' }
$sessionById = @{}
foreach ($session in $chats.sessions) {
    if ($sessionById.ContainsKey($session.session_id)) { Add-Issue "Duplicate chat session: $($session.session_id)" }
    $sessionById[$session.session_id] = $session
    if (-not $laneById.ContainsKey($session.chat_id)) { Add-Issue "Unknown session lane: $($session.chat_id)" }
    if ($session.status -notin @('active', 'checkpoint', 'completed', 'interrupted')) { Add-Issue "Invalid session status: $($session.session_id)" }
    Check-Artifact $session.log_path "$($session.session_id) log"
    foreach ($id in $session.task_ids) {
        if (-not $taskById.ContainsKey($id)) { Add-Issue "Unknown task in session: $id" }
    }
}
$assigned = @{}
foreach ($assignment in $chats.active_assignments) {
    if ($assigned.ContainsKey($assignment.task_id)) { Add-Issue "Duplicate active assignment: $($assignment.task_id)" }
    $assigned[$assignment.task_id] = $true
    if (-not $sessionById.ContainsKey($assignment.session_id) -or -not $taskById.ContainsKey($assignment.task_id)) {
        Add-Issue 'Assignment references unknown task/session'
        continue
    }
    $registered = $sessionById[$assignment.session_id]
    if ($registered.status -notin @('active', 'checkpoint') -or $registered.chat_id -ne $assignment.chat_id -or
        $registered.task_ids -notcontains $assignment.task_id) { Add-Issue "Assignment/session disagree: $($assignment.task_id)" }
    if ($taskById[$assignment.task_id].status -notin @('IN_PROGRESS', 'REVIEW') -or
        $taskById[$assignment.task_id].session_id -ne $assignment.session_id) { Add-Issue "Assignment/task registry disagree: $($assignment.task_id)" }
}

$actualActive = @($board.tasks | Where-Object { $_.status -in @('IN_PROGRESS', 'REVIEW') } | ForEach-Object { $_.id })
$declaredActive = @($state.active_tasks)
if ((($actualActive | Sort-Object) -join ',') -cne (($declaredActive | Sort-Object) -join ',')) {
    Add-Issue 'state.active_tasks disagrees with the task registry'
}
if ($state.next_task_id) {
    if (-not $taskById.ContainsKey($state.next_task_id)) {
        Add-Issue 'state.next_task_id is unknown'
    } else {
        $nextTask = $taskById[$state.next_task_id]
        if ($nextTask.status -eq 'DONE') { Add-Issue 'next_task_id already DONE' }
        if ($nextTask.status -eq 'DEFERRED') { Add-Issue 'next_task_id is DEFERRED' }
        foreach ($dep in $nextTask.dependencies) {
            if ($taskById.ContainsKey($dep) -and $taskById[$dep].status -ne 'DONE') {
                $warnings.Add("Next task $($nextTask.id) awaits $dep")
            }
        }
    }
    if ($handoff -notmatch ('(?m)^NEXT_TASK: ' + [regex]::Escape($state.next_task_id) + '\s*$')) {
        Add-Issue 'HANDOFF NEXT_TASK disagrees with state.next_task_id'
    }
}
Check-Artifact $state.last_session_log 'state.last_session_log'
Check-Artifact $state.handoff_path 'state.handoff_path'
Check-Artifact $state.task_registry_path 'state.task_registry_path'
Check-Artifact $state.model_routing_path 'state.model_routing_path'
Check-Artifact $state.chat_registry_path 'state.chat_registry_path'
if ($state.last_session_log -ne "management/logs/$($state.last_session_id).md") {
    Add-Issue 'last_session_id and log path disagree'
}
foreach ($jsonPath in @('management/state.json', 'management/tasks.json', 'management/model_routing.json', 'management/chat_registry.json')) {
    # Recent PowerShell versions deserialize ISO timestamps into DateTime.
    # Validate the original JSON string so its explicit timezone is preserved.
    $jsonText = Get-Content -LiteralPath (Join-Path $projectRoot $jsonPath) -Raw -Encoding UTF8
    $dateMatch = [regex]::Match($jsonText, '"updated_at"\s*:\s*"([^"]+)"')
    $dateValue = $dateMatch.Groups[1].Value
    try {
        $parsedDate = [DateTimeOffset]::Parse($dateValue)
        if ($dateValue -notmatch '(Z|[+-]\d{2}:\d{2})$') { Add-Issue 'Timestamp lacks timezone' }
    } catch { Add-Issue "Invalid timestamp: $dateValue" }
}
# Validate only documentation locations; never scan raw data, environments or .git.
$mdFiles = @()
foreach ($dir in @('docs', 'management')) {
    $mdFiles += @(Get-ChildItem -LiteralPath (Join-Path $projectRoot $dir) -Recurse -File -Filter '*.md')
}
$mdFiles += @(Get-Item -LiteralPath (Join-Path $projectRoot 'README.md'), (Join-Path $projectRoot 'AGENTS.md'))
foreach ($entry in @('AGENTS.md', 'SCHOLARGRAPH.md')) {
    $entryPath = Join-Path $workspaceRoot $entry
    if (Test-Path -LiteralPath $entryPath) { $mdFiles += Get-Item -LiteralPath $entryPath }
}
$linkCount = 0
foreach ($file in $mdFiles) {
    $content = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8
    $content = [regex]::Replace($content, '(?ms)^' + [char]96 + '{3}.*?^' + [char]96 + '{3}\s*$', '')
    foreach ($match in [regex]::Matches($content, '(?<!!)\[[^\]\r\n]+\]\(([^)\r\n]+)\)')) {
        $target = $match.Groups[1].Value.Trim().Trim('<', '>')
        if ($target -match '^[a-zA-Z][a-zA-Z0-9+.-]*:') { continue }
        $parts = $target -split '#', 2
        if ([string]::IsNullOrWhiteSpace($parts[0])) {
            $linkedPath = $file.FullName
        } else {
            $linkedPath = [IO.Path]::GetFullPath((Join-Path $file.DirectoryName ([Uri]::UnescapeDataString($parts[0]))))
        }
        $linkCount++
        if (-not (Test-Path -LiteralPath $linkedPath)) {
            Add-Issue "Broken link in $($file.Name): $target"
        } elseif ($parts.Count -eq 2 -and $parts[1] -match '^sg-\d{3}$') {
            $linkedText = Get-Content -LiteralPath $linkedPath -Raw -Encoding UTF8
            if ($linkedText -notmatch ('id="' + [regex]::Escape($parts[1]) + '"')) {
                Add-Issue "Missing task anchor in $($file.Name): $target"
            }
        }
    }
}
$coreHours = ($board.tasks | Where-Object { $_.priority -eq 'CORE' } | Measure-Object -Property estimate_human_hours -Sum).Sum
foreach ($warning in $warnings) { Write-Output "WARN: $warning" }
if ($issues.Count -gt 0) {
    foreach ($problem in $issues) { Write-Output "FAIL: $problem" }
    Write-Output "FAILED: $($issues.Count) issue(s)"
    exit 1
}
$counts = @($board.tasks | Group-Object status | Sort-Object Name | ForEach-Object { "$($_.Name)=$($_.Count)" }) -join ', '
Write-Output "PASS: $($board.tasks.Count) tasks; dependency graph acyclic; task cards and state consistent."
Write-Output "PASS: $linkCount local Markdown links checked; evidence and session paths exist."
Write-Output "PASS: $($routeById.Count) model routes match matrix; $($laneById.Count) logical lanes; $($sessionById.Count) registered chat sessions."
Write-Output "Status: $counts"
Write-Output "Core human effort estimate: $coreHours hours; next task: $($state.next_task_id)"
exit 0
