# ERROR ANALYSIS - reading guide for the two members (SG-030)

## How to read a CI row

- `delta` = mean(treatment) - mean(control) over the same queries (paired).
- A 95% CI that contains 0 means: no conclusion either way (not proof of tie).
- Negative results stand: low/negative deltas are kept, never edited.
- Subgroup buckets are exploratory; mind the n.

## Checklist (each member reads all packets, then you compare)

- [ ] Member 1 read all 24 packets + noted failure hypotheses
- [ ] Member 2 read all 24 packets + noted failure hypotheses
- [ ] Disagreements discussed; joint note appended below

## Packets

### scifact:beir:scifact:1024

```json
{
  "packet": "scifact:beir:scifact:1024",
  "query_text": "Recurrent mutations occur frequently within CTCF anchor sites adjacent to oncogenes.",
  "nDCG@10": {
    "bm25": 1.0,
    "tfidf": 1.0,
    "dense": 0.0,
    "hybrid": 0.3562071871080222
  },
  "top3": {
    "bm25": [
      {
        "doc_id": "beir:scifact:5373138",
        "score": 30.4022,
        "title": "3D Chromosome Regulatory Landscape of Human Pluripotent Cells."
      },
      {
        "doc_id": "beir:scifact:24995939",
        "score": 24.5014,
        "title": "Specific sites in the C terminus of CTCF interact with the SA2 subunit of the cohesin complex and are required for cohesin-dependent insulation activity."
      },
      {
        "doc_id": "beir:scifact:8494570",
        "score": 21.4111,
        "title": "Characterization of constitutive CTCF/cohesin loci: a possible role in establishing topological domains in mammalian genomes"
      }
    ],
    "tfidf": [
      {
        "doc_id": "beir:scifact:5373138",
        "score": 0.2346,
        "title": "3D Chromosome Regulatory Landscape of Human Pluripotent Cells."
      },
      {
        "doc_id": "beir:scifact:24995939",
        "score": 0.2064,
        "title": "Specific sites in the C terminus of CTCF interact with the SA2 subunit of the cohesin complex and are required for cohesin-dependent insulation activity."
      },
      {
        "doc_id": "beir:scifact:14530534",
        "score": 0.1971,
        "title": "Comprehensive Identification and Annotation of Cell Type-Specific and Ubiquitous CTCF-Binding Sites in the Human Genome"
      }
    ],
    "dense": [
      {
        "doc_id": "beir:scifact:26672703",
        "score": 0.665,
        "title": "Repeat instability: mechanisms of dynamic mutations"
      },
      {
        "doc_id": "beir:scifact:42520882",
        "score": 0.6613,
        "title": "Slipped (CTG)•(CAG) repeats can be correctly repaired, escape repair or undergo error-prone repair"
      },
      {
        "d
```

### scifact:beir:scifact:1363

```json
{
  "packet": "scifact:beir:scifact:1363",
  "query_text": "Venules have a thinner or absent smooth layer compared to arterioles.",
  "nDCG@10": {
    "bm25": 1.0,
    "tfidf": 0.6309297535714575,
    "dense": 0.0,
    "hybrid": 0.0
  },
  "top3": {
    "bm25": [
      {
        "doc_id": "beir:scifact:8290953",
        "score": 17.4079,
        "title": "Scaffold-based three-dimensional human fibroblast culture provides a structural matrix that supports angiogenesis in infarcted heart tissue."
      },
      {
        "doc_id": "beir:scifact:1122279",
        "score": 15.9211,
        "title": "Endothelium-mediated relaxation of porcine collateral-dependent arterioles is improved by exercise training."
      },
      {
        "doc_id": "beir:scifact:23513718",
        "score": 13.2702,
        "title": "Role of soluble guanylate cyclase in dilator responses of the cerebral microcirculation."
      }
    ],
    "tfidf": [
      {
        "doc_id": "beir:scifact:1122279",
        "score": 0.1201,
        "title": "Endothelium-mediated relaxation of porcine collateral-dependent arterioles is improved by exercise training."
      },
      {
        "doc_id": "beir:scifact:8290953",
        "score": 0.105,
        "title": "Scaffold-based three-dimensional human fibroblast culture provides a structural matrix that supports angiogenesis in infarcted heart tissue."
      },
      {
        "doc_id": "beir:scifact:23513718",
        "score": 0.1049,
        "title": "Role of soluble guanylate cyclase in dilator responses of the cerebral microcirculation."
      }
    ],
    "dense": [
      {
        "doc_id": "beir:scifact:25175997",
        "score": 0.5932,
        "title": "Pulmonary vascular lesions in end-stage idiopathic pulmonary fibrosis: Histopathologic study on lung explant specimens and correlations with pulmonary hemodynam"
      },
      {
        "doc_id": "beir:scifact:79447",
        "score": 0.5848,
        "title": "Arteriolar function in visceral adipos
```

### scifact:beir:scifact:674

```json
{
  "packet": "scifact:beir:scifact:674",
  "query_text": "LDL cholesterol has no involvement in the development of cardiovascular disease.",
  "nDCG@10": {
    "bm25": 1.0,
    "tfidf": 1.0,
    "dense": 0.0,
    "hybrid": 0.3562071871080222
  },
  "top3": {
    "bm25": [
      {
        "doc_id": "beir:scifact:2095573",
        "score": 28.6575,
        "title": "LDL-cholesterol concentrations: a genome-wide association study"
      },
      {
        "doc_id": "beir:scifact:30981192",
        "score": 25.619,
        "title": "How to control residual cardiovascular risk despite statin treatment: focusing on HDL-cholesterol."
      },
      {
        "doc_id": "beir:scifact:7662206",
        "score": 22.5337,
        "title": "A Century of Cholesterol and Coronaries: From Plaques to Genes to Statins"
      }
    ],
    "tfidf": [
      {
        "doc_id": "beir:scifact:2095573",
        "score": 0.2963,
        "title": "LDL-cholesterol concentrations: a genome-wide association study"
      },
      {
        "doc_id": "beir:scifact:7662206",
        "score": 0.2763,
        "title": "A Century of Cholesterol and Coronaries: From Plaques to Genes to Statins"
      },
      {
        "doc_id": "beir:scifact:9814332",
        "score": 0.2599,
        "title": "LDL inhibits the mediation of cholesterol efflux from macrophage foam cells by apoA-I-containing lipoproteins. A putative mechanism for foam cell formation."
      }
    ],
    "dense": [
      {
        "doc_id": "beir:scifact:5698494",
        "score": 0.6883,
        "title": "The benefits of statins in people without established cardiovascular disease but with cardiovascular risk factors: meta-analysis of randomised controlled trials"
      },
      {
        "doc_id": "beir:scifact:9814332",
        "score": 0.6813,
        "title": "LDL inhibits the mediation of cholesterol efflux from macrophage foam cells by apoA-I-containing lipoproteins. A putative mechanism for foam cell formation."
      },
      {
```

### scifact:beir:scifact:303

```json
{
  "packet": "scifact:beir:scifact:303",
  "query_text": "DMRT1 is a sex-determining gene that is epigenetically regulated by the MHM region.",
  "nDCG@10": {
    "bm25": 0.6309297535714575,
    "tfidf": 0.6309297535714575,
    "dense": 0.0,
    "hybrid": 0.38685280723454163
  },
  "top3": {
    "bm25": [
      {
        "doc_id": "beir:scifact:4085204",
        "score": 36.2747,
        "title": "Transcripts of the MHM region on the chicken Z chromosome accumulate as non-coding RNA in the nucleus of female cells adjacent to the DMRT1 locus"
      },
      {
        "doc_id": "beir:scifact:4388470",
        "score": 16.9238,
        "title": "Somatic sex identity is cell-autonomous in the chicken"
      },
      {
        "doc_id": "beir:scifact:23581096",
        "score": 16.7291,
        "title": "Interactions between SRY and SOX genes in mammalian sex determination."
      }
    ],
    "tfidf": [
      {
        "doc_id": "beir:scifact:4085204",
        "score": 0.338,
        "title": "Transcripts of the MHM region on the chicken Z chromosome accumulate as non-coding RNA in the nucleus of female cells adjacent to the DMRT1 locus"
      },
      {
        "doc_id": "beir:scifact:4388470",
        "score": 0.1127,
        "title": "Somatic sex identity is cell-autonomous in the chicken"
      },
      {
        "doc_id": "beir:scifact:23581096",
        "score": 0.0999,
        "title": "Interactions between SRY and SOX genes in mammalian sex determination."
      }
    ],
    "dense": [
      {
        "doc_id": "beir:scifact:4085204",
        "score": 0.7226,
        "title": "Transcripts of the MHM region on the chicken Z chromosome accumulate as non-coding RNA in the nucleus of female cells adjacent to the DMRT1 locus"
      },
      {
        "doc_id": "beir:scifact:5278233",
        "score": 0.6469,
        "title": "A maternally methylated CpG island in KvLQT1 is associated with an antisense paternal transcript and loss of imprinting in Beckwith-Wiedemann 
```

### scifact:beir:scifact:294

```json
{
  "packet": "scifact:beir:scifact:294",
  "query_text": "Crossover hot spots are not found within gene promoters in Saccharomyces cerevisiae.",
  "nDCG@10": {
    "bm25": 1.0,
    "tfidf": 1.0,
    "dense": 0.43067655807339306,
    "hybrid": 1.0
  },
  "top3": {
    "bm25": [
      {
        "doc_id": "beir:scifact:10874408",
        "score": 26.9931,
        "title": "Mapping Meiotic Single-Strand DNA Reveals a New Landscape of DNA Double-Strand Breaks in Saccharomyces cerevisiae"
      },
      {
        "doc_id": "beir:scifact:32638085",
        "score": 22.6132,
        "title": "Histone acetylation and deacetylation in yeast"
      },
      {
        "doc_id": "beir:scifact:21170174",
        "score": 19.6105,
        "title": "Crossover and noncrossover pathways in mouse meiosis."
      }
    ],
    "tfidf": [
      {
        "doc_id": "beir:scifact:10874408",
        "score": 0.1642,
        "title": "Mapping Meiotic Single-Strand DNA Reveals a New Landscape of DNA Double-Strand Breaks in Saccharomyces cerevisiae"
      },
      {
        "doc_id": "beir:scifact:32638085",
        "score": 0.1537,
        "title": "Histone acetylation and deacetylation in yeast"
      },
      {
        "doc_id": "beir:scifact:13949015",
        "score": 0.1381,
        "title": "LINE-1 Retrotransposition Activity in Human Genomes"
      }
    ],
    "dense": [
      {
        "doc_id": "beir:scifact:10766688",
        "score": 0.6676,
        "title": "Sperm cross-over activity in regions of the human genome showing extreme breakdown of marker association."
      },
      {
        "doc_id": "beir:scifact:21170174",
        "score": 0.6551,
        "title": "Crossover and noncrossover pathways in mouse meiosis."
      },
      {
        "doc_id": "beir:scifact:17240457",
        "score": 0.6429,
        "title": "A comprehensive genomic binding map of gene and chromatin regulatory proteins in Saccharomyces."
      }
    ],
    "hybrid": [
      {
        "doc_id": "beir:sc
```

### scifact:beir:scifact:587

```json
{
  "packet": "scifact:beir:scifact:587",
  "query_text": "In transgenic mice harboring green florescent protein under the control of the Sox2 promoter, less than ten percent of the cells with green florescent colocalize with cell proliferation markers.",
  "nDCG@10": {
    "bm25": 1.0,
    "tfidf": 1.0,
    "dense": 0.43067655807339306,
    "hybrid": 1.0
  },
  "top3": {
    "bm25": [
      {
        "doc_id": "beir:scifact:16999023",
        "score": 29.8976,
        "title": "Cell Stem Cell Article In Vivo Fate Analysis Reveals the Multipotent and Self-Renewal Capacities of Sox2 + Neural Stem Cells in the Adult Hippocampus"
      },
      {
        "doc_id": "beir:scifact:2559303",
        "score": 28.6665,
        "title": "Engraftment of engineered ES cell–derived cardiomyocytes but not BM cells restores contractile function to the infarcted myocardium"
      },
      {
        "doc_id": "beir:scifact:21230110",
        "score": 27.8624,
        "title": "A promoter derived from taro bacilliform badnavirus drives strong expression in transgenic banana and tobacco plants"
      }
    ],
    "tfidf": [
      {
        "doc_id": "beir:scifact:16999023",
        "score": 0.1837,
        "title": "Cell Stem Cell Article In Vivo Fate Analysis Reveals the Multipotent and Self-Renewal Capacities of Sox2 + Neural Stem Cells in the Adult Hippocampus"
      },
      {
        "doc_id": "beir:scifact:2296264",
        "score": 0.1706,
        "title": "Modulation of cancer chemotherapy by green tea."
      },
      {
        "doc_id": "beir:scifact:40558887",
        "score": 0.1538,
        "title": "Expression of green fluorescent protein in the ureteric bud of transgenic mice: a new tool for the analysis of ureteric bud morphogenesis."
      }
    ],
    "dense": [
      {
        "doc_id": "beir:scifact:40558887",
        "score": 0.712,
        "title": "Expression of green fluorescent protein in the ureteric bud of transgenic mice: a new tool for the analysis of uret
```

### scifact:beir:scifact:1

```json
{
  "packet": "scifact:beir:scifact:1",
  "query_text": "0-dimensional biomaterials show inductive properties.",
  "nDCG@10": {
    "bm25": 0.0,
    "tfidf": 0.0,
    "dense": 0.0,
    "hybrid": 0.0
  },
  "top3": {
    "bm25": [
      {
        "doc_id": "beir:scifact:10608397",
        "score": 10.5575,
        "title": "High-performance neuroprosthetic control by an individual with tetraplegia."
      },
      {
        "doc_id": "beir:scifact:43385013",
        "score": 10.1311,
        "title": "Epithelial and mesenchymal subpopulations within normal basal breast cell lines exhibit distinct stem cell/progenitor properties."
      },
      {
        "doc_id": "beir:scifact:40212412",
        "score": 9.6289,
        "title": "Periosteal bone formation--a neglected determinant of bone strength."
      }
    ],
    "tfidf": [
      {
        "doc_id": "beir:scifact:10931595",
        "score": 0.0771,
        "title": "Geometry, epistasis, and developmental patterning."
      },
      {
        "doc_id": "beir:scifact:13231899",
        "score": 0.0752,
        "title": "In situ regulation of DC subsets and T cells mediates tumor regression in mice."
      },
      {
        "doc_id": "beir:scifact:24998637",
        "score": 0.072,
        "title": "Interleukin 6 plays a key role in the development of antigen-induced arthritis."
      }
    ],
    "dense": [
      {
        "doc_id": "beir:scifact:14103509",
        "score": 0.5819,
        "title": "Mechanistic Fracture Criteria For The Failure Of Human Cortical Bone"
      },
      {
        "doc_id": "beir:scifact:21456232",
        "score": 0.5779,
        "title": "A graphene-based platform for induced pluripotent stem cells culture and differentiation."
      },
      {
        "doc_id": "beir:scifact:4346436",
        "score": 0.571,
        "title": "Nonlinear Elasticity in Biological Gels"
      }
    ],
    "hybrid": [
      {
        "doc_id": "beir:scifact:10931595",
        "score": 0.0225,
        "t
```

### scifact:beir:scifact:1024

```json
{
  "packet": "scifact:beir:scifact:1024",
  "query_text": "Recurrent mutations occur frequently within CTCF anchor sites adjacent to oncogenes.",
  "nDCG@10": {
    "bm25": 1.0,
    "tfidf": 1.0,
    "dense": 0.0,
    "hybrid": 0.3562071871080222
  },
  "top3": {
    "bm25": [
      {
        "doc_id": "beir:scifact:5373138",
        "score": 30.4022,
        "title": "3D Chromosome Regulatory Landscape of Human Pluripotent Cells."
      },
      {
        "doc_id": "beir:scifact:24995939",
        "score": 24.5014,
        "title": "Specific sites in the C terminus of CTCF interact with the SA2 subunit of the cohesin complex and are required for cohesin-dependent insulation activity."
      },
      {
        "doc_id": "beir:scifact:8494570",
        "score": 21.4111,
        "title": "Characterization of constitutive CTCF/cohesin loci: a possible role in establishing topological domains in mammalian genomes"
      }
    ],
    "tfidf": [
      {
        "doc_id": "beir:scifact:5373138",
        "score": 0.2346,
        "title": "3D Chromosome Regulatory Landscape of Human Pluripotent Cells."
      },
      {
        "doc_id": "beir:scifact:24995939",
        "score": 0.2064,
        "title": "Specific sites in the C terminus of CTCF interact with the SA2 subunit of the cohesin complex and are required for cohesin-dependent insulation activity."
      },
      {
        "doc_id": "beir:scifact:14530534",
        "score": 0.1971,
        "title": "Comprehensive Identification and Annotation of Cell Type-Specific and Ubiquitous CTCF-Binding Sites in the Human Genome"
      }
    ],
    "dense": [
      {
        "doc_id": "beir:scifact:26672703",
        "score": 0.665,
        "title": "Repeat instability: mechanisms of dynamic mutations"
      },
      {
        "doc_id": "beir:scifact:42520882",
        "score": 0.6613,
        "title": "Slipped (CTG)•(CAG) repeats can be correctly repaired, escape repair or undergo error-prone repair"
      },
      {
        "d
```

### scifact:beir:scifact:1110

```json
{
  "packet": "scifact:beir:scifact:1110",
  "query_text": "Suboptimal nutrition is not predictive of chronic disease",
  "nDCG@10": {
    "bm25": 0.0,
    "tfidf": 0.0,
    "dense": 0.0,
    "hybrid": 0.0
  },
  "top3": {
    "bm25": [
      {
        "doc_id": "beir:scifact:756887",
        "score": 16.6962,
        "title": "A comparison of cancer screening practices in cancer survivors and in the general population: the Korean national health and nutrition examination survey (KNHAN"
      },
      {
        "doc_id": "beir:scifact:23983289",
        "score": 14.2432,
        "title": "Accuracy of ICD-9-CM codes for identifying cardiovascular and stroke risk factors."
      },
      {
        "doc_id": "beir:scifact:10010651",
        "score": 12.7765,
        "title": "Nutrition and physical activity guidelines for cancer survivors."
      }
    ],
    "tfidf": [
      {
        "doc_id": "beir:scifact:43128141",
        "score": 0.1975,
        "title": "Enteral nutrition in the critically ill patient."
      },
      {
        "doc_id": "beir:scifact:756887",
        "score": 0.1672,
        "title": "A comparison of cancer screening practices in cancer survivors and in the general population: the Korean national health and nutrition examination survey (KNHAN"
      },
      {
        "doc_id": "beir:scifact:10010651",
        "score": 0.1552,
        "title": "Nutrition and physical activity guidelines for cancer survivors."
      }
    ],
    "dense": [
      {
        "doc_id": "beir:scifact:8529693",
        "score": 0.6545,
        "title": "Maternal and child undernutrition: consequences for adult health and human capital"
      },
      {
        "doc_id": "beir:scifact:24273592",
        "score": 0.6535,
        "title": "Dietary quality among men and women in 187 countries in 1990 and 2010: a systematic assessment"
      },
      {
        "doc_id": "beir:scifact:3828508",
        "score": 0.6427,
        "title": "Overweight in Celiac Disease: Preval
```

### scifact:beir:scifact:1175

```json
{
  "packet": "scifact:beir:scifact:1175",
  "query_text": "The PPR MDA5 has two N-terminal CARD domains.",
  "nDCG@10": {
    "bm25": 0.0,
    "tfidf": 0.0,
    "dense": 0.0,
    "hybrid": 0.0
  },
  "top3": {
    "bm25": [
      {
        "doc_id": "beir:scifact:22191759",
        "score": 19.1288,
        "title": "Purification and structural characterization of bovine cathelicidins, precursors of antimicrobial peptides."
      },
      {
        "doc_id": "beir:scifact:38899659",
        "score": 16.663,
        "title": "PTH Signaling in Osteoprogenitors Is Essential for B-Lymphocyte Differentiation and Mobilization."
      },
      {
        "doc_id": "beir:scifact:16058322",
        "score": 16.1149,
        "title": "MDA5 and PTPN2, two candidate genes for type 1 diabetes, modify pancreatic β-cell responses to the viral by-product double-stranded RNA"
      }
    ],
    "tfidf": [
      {
        "doc_id": "beir:scifact:38899659",
        "score": 0.2009,
        "title": "PTH Signaling in Osteoprogenitors Is Essential for B-Lymphocyte Differentiation and Mobilization."
      },
      {
        "doc_id": "beir:scifact:16058322",
        "score": 0.1415,
        "title": "MDA5 and PTPN2, two candidate genes for type 1 diabetes, modify pancreatic β-cell responses to the viral by-product double-stranded RNA"
      },
      {
        "doc_id": "beir:scifact:2566674",
        "score": 0.128,
        "title": "Ribose 2′-O-methylation provides a molecular signature for the distinction of self and non-self mRNA dependent on the RNA sensor Mda5"
      }
    ],
    "dense": [
      {
        "doc_id": "beir:scifact:14474178",
        "score": 0.52,
        "title": "Role of chicken melanoma differentiation-associated gene 5 in induction and activation of innate and adaptive immune responses to infectious bursal disease viru"
      },
      {
        "doc_id": "beir:scifact:16058322",
        "score": 0.5129,
        "title": "MDA5 and PTPN2, two candidate genes for ty
```

### scifact:beir:scifact:1179

```json
{
  "packet": "scifact:beir:scifact:1179",
  "query_text": "The PRR MDA5 has a central DExD/H RNA helices domain.",
  "nDCG@10": {
    "bm25": 0.2890648263178879,
    "tfidf": 0.3010299956639812,
    "dense": 0.0,
    "hybrid": 0.3010299956639812
  },
  "top3": {
    "bm25": [
      {
        "doc_id": "beir:scifact:10627801",
        "score": 36.7441,
        "title": "Loss of DExD/H box RNA helicase LGP2 manifests disparate antiviral responses."
      },
      {
        "doc_id": "beir:scifact:1569031",
        "score": 17.7719,
        "title": "RNase H and Postreplication Repair Protect Cells from Ribonucleotides Incorporated in DNA"
      },
      {
        "doc_id": "beir:scifact:16058322",
        "score": 17.003,
        "title": "MDA5 and PTPN2, two candidate genes for type 1 diabetes, modify pancreatic β-cell responses to the viral by-product double-stranded RNA"
      }
    ],
    "tfidf": [
      {
        "doc_id": "beir:scifact:10627801",
        "score": 0.2825,
        "title": "Loss of DExD/H box RNA helicase LGP2 manifests disparate antiviral responses."
      },
      {
        "doc_id": "beir:scifact:2566674",
        "score": 0.1493,
        "title": "Ribose 2′-O-methylation provides a molecular signature for the distinction of self and non-self mRNA dependent on the RNA sensor Mda5"
      },
      {
        "doc_id": "beir:scifact:16058322",
        "score": 0.1363,
        "title": "MDA5 and PTPN2, two candidate genes for type 1 diabetes, modify pancreatic β-cell responses to the viral by-product double-stranded RNA"
      }
    ],
    "dense": [
      {
        "doc_id": "beir:scifact:10627801",
        "score": 0.6309,
        "title": "Loss of DExD/H box RNA helicase LGP2 manifests disparate antiviral responses."
      },
      {
        "doc_id": "beir:scifact:10029970",
        "score": 0.6118,
        "title": "CDD: conserved domains and protein three-dimensional structure"
      },
      {
        "doc_id": "beir:scifact:14474178",
    
```

### scifact:beir:scifact:1199

```json
{
  "packet": "scifact:beir:scifact:1199",
  "query_text": "The benefits of colchicine were achieved with effective widespread use of secondary prevention strategies such as high-dose statins.",
  "nDCG@10": {
    "bm25": 0.0,
    "tfidf": 0.0,
    "dense": 0.0,
    "hybrid": 0.0
  },
  "top3": {
    "bm25": [
      {
        "doc_id": "beir:scifact:7454794",
        "score": 39.657,
        "title": "Statins in the primary prevention of cardiovascular disease"
      },
      {
        "doc_id": "beir:scifact:8708082",
        "score": 26.32,
        "title": "The prevention of type 2 diabetes"
      },
      {
        "doc_id": "beir:scifact:21557614",
        "score": 25.7256,
        "title": "Pleiotropic effects of statins."
      }
    ],
    "tfidf": [
      {
        "doc_id": "beir:scifact:7454794",
        "score": 0.2794,
        "title": "Statins in the primary prevention of cardiovascular disease"
      },
      {
        "doc_id": "beir:scifact:21557614",
        "score": 0.2112,
        "title": "Pleiotropic effects of statins."
      },
      {
        "doc_id": "beir:scifact:8708082",
        "score": 0.1562,
        "title": "The prevention of type 2 diabetes"
      }
    ],
    "dense": [
      {
        "doc_id": "beir:scifact:7454794",
        "score": 0.6863,
        "title": "Statins in the primary prevention of cardiovascular disease"
      },
      {
        "doc_id": "beir:scifact:40156901",
        "score": 0.6488,
        "title": "Dose-dependent effect of statins on the incidence of acute kidney injury after cardiac surgery."
      },
      {
        "doc_id": "beir:scifact:4687948",
        "score": 0.6455,
        "title": "HMG-CoA reductase inhibitors and the risk of hip fractures in elderly patients."
      }
    ],
    "hybrid": [
      {
        "doc_id": "beir:scifact:7454794",
        "score": 0.0328,
        "title": "Statins in the primary prevention of cardiovascular disease"
      },
      {
        "doc_id": "beir:scifact:401
```

### scidocs:beir:scidocs:fcd16bfffd4131b2f41f90b4c832415aea55038b

```json
{
  "packet": "scidocs:beir:scidocs:fcd16bfffd4131b2f41f90b4c832415aea55038b",
  "query_text": "Auto-Conditioned Recurrent Networks for Extended Complex Human Motion Synthesis",
  "nDCG@10": {
    "bm25": 0.48160565320269266,
    "dense": 0.0,
    "hybrid": 0.14606834984270645
  },
  "top3": {
    "bm25": [
      {
        "doc_id": "beir:scidocs:8027f50bbcee3938196c6d5519464df16c275f8d",
        "score": 27.9281,
        "title": "On Human Motion Prediction Using Recurrent Neural Networks"
      },
      {
        "doc_id": "beir:scidocs:652d159bf64a70194127722d19841daa99a69b64",
        "score": 24.982,
        "title": "Generating Sequences With Recurrent Neural Networks"
      },
      {
        "doc_id": "beir:scidocs:26d4ab9b60b91bb610202b58fa1766951fedb9e9",
        "score": 23.2918,
        "title": "DRAW: A Recurrent Neural Network For Image Generation"
      }
    ],
    "dense": [
      {
        "doc_id": "beir:scidocs:8027f50bbcee3938196c6d5519464df16c275f8d",
        "score": 0.812,
        "title": "On Human Motion Prediction Using Recurrent Neural Networks"
      },
      {
        "doc_id": "beir:scidocs:8f2576492e468342659e3963fef17eee785ccac2",
        "score": 0.7976,
        "title": "Human Motion Reconstruction from Action Video Data Using a 3-Layer-LSTM"
      },
      {
        "doc_id": "beir:scidocs:aa0c01e553d0a1ab40c204725d13fe528c514bba",
        "score": 0.7815,
        "title": "Anticipating many futures: Online human motion prediction and synthesis for human-robot collaboration"
      }
    ],
    "hybrid": [
      {
        "doc_id": "beir:scidocs:8027f50bbcee3938196c6d5519464df16c275f8d",
        "score": 0.0328,
        "title": "On Human Motion Prediction Using Recurrent Neural Networks"
      },
      {
        "doc_id": "beir:scidocs:8f2576492e468342659e3963fef17eee785ccac2",
        "score": 0.0318,
        "title": "Human Motion Reconstruction from Action Video Data Using a 3-Layer-LSTM"
      },
      {
        "doc_id": "bei
```

### scidocs:beir:scidocs:5358924a48392d24e28afe850fa6849eaa1665d9

```json
{
  "packet": "scidocs:beir:scidocs:5358924a48392d24e28afe850fa6849eaa1665d9",
  "query_text": "Argumentative Zoning for Improved Citation Indexing",
  "nDCG@10": {
    "bm25": 0.38356636737133565,
    "dense": 0.0,
    "hybrid": 0.21398626473452756
  },
  "top3": {
    "bm25": [
      {
        "doc_id": "beir:scidocs:f82d90b5b19db754bec5bf4354eaaf21e5e6d20e",
        "score": 26.5147,
        "title": "Towards Discipline-Independent Argumentative Zoning : Evidence from Chemistry and Computational Linguistics"
      },
      {
        "doc_id": "beir:scidocs:19b6df414753a81e2fbb1030ddd983210ea4ec80",
        "score": 22.0749,
        "title": "Digital Libraries and Autonomous Citation Indexing"
      },
      {
        "doc_id": "beir:scidocs:56d36c2535c867613997688f649cf0461171dbe8",
        "score": 17.8452,
        "title": "CiteSeer: An Automatic Citation Indexing System"
      }
    ],
    "dense": [
      {
        "doc_id": "beir:scidocs:f82d90b5b19db754bec5bf4354eaaf21e5e6d20e",
        "score": 0.8322,
        "title": "Towards Discipline-Independent Argumentative Zoning : Evidence from Chemistry and Computational Linguistics"
      },
      {
        "doc_id": "beir:scidocs:158d54518e694d0a7d7c0fe2ea474d873eaeb5a0",
        "score": 0.7833,
        "title": "ArgumenText: Searching for Arguments in Heterogeneous Sources"
      },
      {
        "doc_id": "beir:scidocs:6de1fbfe86ddfef72d5fcfdb6e7e140be0ab195e",
        "score": 0.7683,
        "title": "Argumentation Mining: Where are we now, where do we want to be and how do we get there?"
      }
    ],
    "hybrid": [
      {
        "doc_id": "beir:scidocs:f82d90b5b19db754bec5bf4354eaaf21e5e6d20e",
        "score": 0.0328,
        "title": "Towards Discipline-Independent Argumentative Zoning : Evidence from Chemistry and Computational Linguistics"
      },
      {
        "doc_id": "beir:scidocs:56d36c2535c867613997688f649cf0461171dbe8",
        "score": 0.0285,
        "title": "CiteSeer: An Automatic
```

### scidocs:beir:scidocs:9003fb79e7848ced3be975c3d87a9348a4b8d377

```json
{
  "packet": "scidocs:beir:scidocs:9003fb79e7848ced3be975c3d87a9348a4b8d377",
  "query_text": "Moral development, executive functioning, peak experiences and brain patterns in professional and amateur classical musicians: Interpreted in light of a Unified Theory of Performance",
  "nDCG@10": {
    "bm25": 0.5205067333228022,
    "dense": 0.15101961822780524,
    "hybrid": 0.5413996682199069
  },
  "top3": {
    "bm25": [
      {
        "doc_id": "beir:scidocs:8ed0ee88e811aaaad56d1a42e2cfce02edcc90ff",
        "score": 33.8973,
        "title": "Brain structures differ between musicians and non-musician"
      },
      {
        "doc_id": "beir:scidocs:6c3877672f52dac3ed34be1614c981775d1779da",
        "score": 27.2314,
        "title": "Less-structured time in children's daily lives predicts self-directed executive functioning"
      },
      {
        "doc_id": "beir:scidocs:ba94e00c5c2e7cf78307b1fdfb2b623cceca7e86",
        "score": 23.4435,
        "title": "The neural basis of intuitive best next-move generation in board game experts."
      }
    ],
    "dense": [
      {
        "doc_id": "beir:scidocs:32231cecd7a740f6914b9896709188c0d876320c",
        "score": 0.7245,
        "title": "Maintaining excellence: deliberate practice and elite performance in young and older pianists."
      },
      {
        "doc_id": "beir:scidocs:336222eedc745e17f85cc85141891ed3b48b9ef7",
        "score": 0.7091,
        "title": "Moderating variables of music training-induced neuroplasticity: a review and discussion"
      },
      {
        "doc_id": "beir:scidocs:7c5adcf159af8df4d91774b196fb32189efc0368",
        "score": 0.7079,
        "title": "Expertise-related deactivation of the right temporoparietal junction during musical improvisation"
      }
    ],
    "hybrid": [
      {
        "doc_id": "beir:scidocs:8ed0ee88e811aaaad56d1a42e2cfce02edcc90ff",
        "score": 0.0318,
        "title": "Brain structures differ between musicians and non-musician"
      },
      
```

### scidocs:beir:scidocs:012e396b02aa584cb74a65ae14af355e7c897858

```json
{
  "packet": "scidocs:beir:scidocs:012e396b02aa584cb74a65ae14af355e7c897858",
  "query_text": "Efficient and secure data storage operations for mobile cloud computing",
  "nDCG@10": {
    "bm25": 0.0,
    "dense": 0.0,
    "hybrid": 0.0
  },
  "top3": {
    "bm25": [
      {
        "doc_id": "beir:scidocs:af77547dc79c67367675e76f28c3bbf3032a9a12",
        "score": 38.1064,
        "title": "Secure data processing framework for mobile cloud computing"
      },
      {
        "doc_id": "beir:scidocs:3ffdcfdd7511beab79539a96c2ae805c40160a36",
        "score": 32.5803,
        "title": "Twin Clouds: An Architecture for Secure Cloud Computing (Extended Abstract)"
      },
      {
        "doc_id": "beir:scidocs:4c9774c5e57a4b7535eb19f6584f75c8b9c2cdcc",
        "score": 30.8034,
        "title": "A framework based on RSA and AES encryption algorithms for cloud computing services"
      }
    ],
    "dense": [
      {
        "doc_id": "beir:scidocs:af77547dc79c67367675e76f28c3bbf3032a9a12",
        "score": 0.7776,
        "title": "Secure data processing framework for mobile cloud computing"
      },
      {
        "doc_id": "beir:scidocs:6d3a038660e2961e1f87fe7d5ae2dd56dee87fee",
        "score": 0.7736,
        "title": "MobiCloud: A geo-distributed mobile cloud computing platform"
      },
      {
        "doc_id": "beir:scidocs:541c3ab3ce75594c403126413b9c866fa7fba57a",
        "score": 0.7719,
        "title": "Help your mobile applications with fog computing"
      }
    ],
    "hybrid": [
      {
        "doc_id": "beir:scidocs:af77547dc79c67367675e76f28c3bbf3032a9a12",
        "score": 0.0328,
        "title": "Secure data processing framework for mobile cloud computing"
      },
      {
        "doc_id": "beir:scidocs:3ffdcfdd7511beab79539a96c2ae805c40160a36",
        "score": 0.0313,
        "title": "Twin Clouds: An Architecture for Secure Cloud Computing (Extended Abstract)"
      },
      {
        "doc_id": "beir:scidocs:541c3ab3ce75594c403126413b9c866
```

### scidocs:beir:scidocs:01d208b33561362f7714f714d3bc4a1f7aa1637c

```json
{
  "packet": "scidocs:beir:scidocs:01d208b33561362f7714f714d3bc4a1f7aa1637c",
  "query_text": "Bank distress in the news: Describing events through deep learning",
  "nDCG@10": {
    "bm25": 0.0,
    "dense": 0.0,
    "hybrid": 0.0
  },
  "top3": {
    "bm25": [
      {
        "doc_id": "beir:scidocs:02dd5b65dfc005c30c2c4f49ba5afb586cd7770c",
        "score": 21.1017,
        "title": "Event Detection in Social Media Detecting"
      },
      {
        "doc_id": "beir:scidocs:7687a755350038675f0a663e7ff5e7a8f6274bdb",
        "score": 20.6268,
        "title": "Reuters Tracer: A Large Scale System of Detecting & Verifying Real-Time News Events from Twitter"
      },
      {
        "doc_id": "beir:scidocs:8f67ff7d7a4fc72d87f82ae340dba4365b7ea664",
        "score": 18.9039,
        "title": "Learning Filter Banks Using Deep Learning For Acoustic Signals"
      }
    ],
    "dense": [
      {
        "doc_id": "beir:scidocs:8645a7ff78dc321e08dea6576c04f02a3ce158f9",
        "score": 0.6971,
        "title": "Sequential Deep Learning for Disaster-Related Video Classification"
      },
      {
        "doc_id": "beir:scidocs:4938e8c8c9ea3d351d283181819af5e5801efbed",
        "score": 0.6926,
        "title": "Deep Learning for Event-Driven Stock Prediction"
      },
      {
        "doc_id": "beir:scidocs:4b53f660eb6cfe9180f9e609ad94df8606724a3d",
        "score": 0.691,
        "title": "Text mining of news-headlines for FOREX market prediction: A Multi-layer Dimension Reduction Algorithm with semantics and sentiment"
      }
    ],
    "hybrid": [
      {
        "doc_id": "beir:scidocs:34329c7ec1cc159ed5efa84cb38ea9bbec335d19",
        "score": 0.0299,
        "title": "A probabilistic model for retrospective news event detection"
      },
      {
        "doc_id": "beir:scidocs:048e82ac9c88c458a50cc6289662e9cb2ecb4fc9",
        "score": 0.0297,
        "title": "A Multiple Instance Learning Framework for Identifying Key Sentences and Detecting Events"
      },
   
```

### scidocs:beir:scidocs:031a0f18d46b8e006eb4262233f7734fe4505c21

```json
{
  "packet": "scidocs:beir:scidocs:031a0f18d46b8e006eb4262233f7734fe4505c21",
  "query_text": "AntNet: Distributed Stigmergetic Control for Communications Networks",
  "nDCG@10": {
    "bm25": 0.0,
    "dense": 0.0,
    "hybrid": 0.0
  },
  "top3": {
    "bm25": [
      {
        "doc_id": "beir:scidocs:3646caf12ff38117a0f1b0d4470c034e15021021",
        "score": 17.1342,
        "title": "Q-Learning-Based Power Control for LTE Enterprise Femtocell Networks"
      },
      {
        "doc_id": "beir:scidocs:0bb71e91b29cf9739c0e1334f905baad01b663e6",
        "score": 16.4792,
        "title": "Lifetime-Aware Scheduling and Power Control for M2M Communications in LTE Networks"
      },
      {
        "doc_id": "beir:scidocs:7a6f802c089c339256dcbff9d3039abbe60ea076",
        "score": 15.5209,
        "title": "LTE-V for Sidelink 5G V2X Vehicular Communications: A New 5G Technology for Short-Range Vehicle-to-Everything Communications"
      }
    ],
    "dense": [
      {
        "doc_id": "beir:scidocs:f77f1d1d274042105cceebf17a57e680dfe1ce03",
        "score": 0.6787,
        "title": "Ant colony optimization for routing and load-balancing: survey and new directions"
      },
      {
        "doc_id": "beir:scidocs:63f37950b5adfe7d90baa6284e4fc4e2edacbcc6",
        "score": 0.6768,
        "title": "Learning Multi-agent Communication under Limited-bandwidth Restriction for Internet Packet Routing"
      },
      {
        "doc_id": "beir:scidocs:0e9a674280b2dabe36e540c20ce5a7a9e10361f7",
        "score": 0.675,
        "title": "Enhancing network performance in Distributed Cognitive Radio Networks using single-agent and multi-agent Reinforcement Learning"
      }
    ],
    "hybrid": [
      {
        "doc_id": "beir:scidocs:3c03973d488666fa61a2c7dad65f8e0dea24b012",
        "score": 0.0239,
        "title": "Distributed Optimization for Model Predictive Control of Linear Dynamic Networks With Control-Input and Output Constraints"
      },
      {
        "doc_id": "b
```

### trackB:openalex:W4409150968

```json
{
  "packet": "trackB:openalex:W4409150968",
  "query_source": "openalex:W4409150968",
  "ppr_nDCG@10": 1.0,
  "global_nDCG@10": 0.6309297535714575,
  "heldout": [
    "openalex:W4289527972"
  ],
  "ppr_top3": [
    "openalex:W4289527972",
    "openalex:W4403039705",
    "openalex:W4410832041"
  ],
  "global_top3": [
    "openalex:W3028991364",
    "openalex:W4289527972",
    "openalex:W4403039705"
  ]
}
```

### trackB:openalex:W4414568621

```json
{
  "packet": "trackB:openalex:W4414568621",
  "query_source": "openalex:W4414568621",
  "ppr_nDCG@10": 0.43067655807339306,
  "global_nDCG@10": 0.38685280723454163,
  "heldout": [
    "openalex:W4401283433"
  ],
  "ppr_top3": [
    "openalex:W4323042481",
    "openalex:W4293731506",
    "openalex:W4318921106"
  ],
  "global_top3": [
    "openalex:W4323042481",
    "openalex:W4294335603",
    "openalex:W4293731506"
  ]
}
```

### trackB:openalex:W4416018140

```json
{
  "packet": "trackB:openalex:W4416018140",
  "query_source": "openalex:W4416018140",
  "ppr_nDCG@10": 0.3562071871080222,
  "global_nDCG@10": 0.31546487678572877,
  "heldout": [
    "openalex:W4280604273"
  ],
  "ppr_top3": [
    "openalex:W3038598309",
    "openalex:W4281855903",
    "openalex:W3212549986"
  ],
  "global_top3": [
    "openalex:W3038598309",
    "openalex:W4281855903",
    "openalex:W3212549986"
  ]
}
```

### trackB:openalex:W4406047910

```json
{
  "packet": "trackB:openalex:W4406047910",
  "query_source": "openalex:W4406047910",
  "ppr_nDCG@10": 0.0,
  "global_nDCG@10": 0.0,
  "heldout": [
    "openalex:W1678356000"
  ],
  "ppr_top3": [
    "openalex:W3093598039",
    "openalex:W3165069287",
    "openalex:W2989988375"
  ],
  "global_top3": [
    "openalex:W3093598039",
    "openalex:W2989988375",
    "openalex:W3165069287"
  ]
}
```

### trackB:openalex:W4406063828

```json
{
  "packet": "trackB:openalex:W4406063828",
  "query_source": "openalex:W4406063828",
  "ppr_nDCG@10": 0.0,
  "global_nDCG@10": 0.0,
  "heldout": [
    "openalex:W4213009331"
  ],
  "ppr_top3": [
    "openalex:W3098772815",
    "openalex:W4404585682",
    "openalex:W3137858141"
  ],
  "global_top3": [
    "openalex:W3098772815",
    "openalex:W4404585682",
    "openalex:W3137858141"
  ]
}
```

### trackB:openalex:W4406106681

```json
{
  "packet": "trackB:openalex:W4406106681",
  "query_source": "openalex:W4406106681",
  "ppr_nDCG@10": 0.0,
  "global_nDCG@10": 0.0,
  "heldout": [
    "openalex:W1678356000"
  ],
  "ppr_top3": [
    "openalex:W4391770459",
    "openalex:W4406130598",
    "openalex:W4292202394"
  ],
  "global_top3": [
    "openalex:W4391770459",
    "openalex:W4406130598",
    "openalex:W4292202394"
  ]
}
```

## Joint note (to be filled by the two members)

(pending)
