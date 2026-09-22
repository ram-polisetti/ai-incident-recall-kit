# Regulatory field mapping — EU AI Act Article 73

`report.py` assembles the serious-incident report in the shape of the
EU AI Act's serious-incident reporting duty (Article 73): providers of
high-risk AI systems must inform the market surveillance authority of
serious incidents, describing the system, the incident, its severity and
consequences, and the corrective action taken or envisaged.

| Report field | Art. 73 concept | Source in the pipeline |
|---|---|---|
| `provider.{name, contact}` | provider identity | `provider.json` (operator-supplied) |
| `system.{name, incident_version, rolled_back_to_version, deployment}` | AI system identification | incident record + rollback plan |
| `incident.{id, severity, detected_at, detection_source}` | incident identification | audit log + alert |
| `description` | what happened | assembled from alert + rollback |
| `evidence.breaching_metrics` | supporting evidence | disparity-monitor alert verbatim |
| `affected_persons_estimate` | severity / consequences | `provider.json` (operator estimate) |
| `root_cause_preliminary` | causes, if known | remediation record / CAP |
| `corrective_actions_taken` | measures taken | remediation record |
| `corrective_actions_planned` | measures envisaged | corrective-action plan |
| `cross_border_relevance` | cross-border implications | `provider.json` |
| `audit_chain.{records, verified}` | traceability | hash-chain verification |

What this mapping does **not** do: decide whether an incident meets the
legal threshold of "serious", determine the competent authority or filing
deadline, or constitute legal advice. Those are human decisions made at
filing time; the report exists so the human files from complete facts.
