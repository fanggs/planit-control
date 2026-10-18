# Heat-index interpretation for Alan and Aryan (#19)

Sid's calculation is `get_data/weather_values.py:heat_index_f`. It implements
NWS Rothfusz regression with humidity adjustments. Its **conservative project
calculation domain** is temperature **80–112 °F inclusive**, relative humidity
**0–100% inclusive**, and the NWS initial screening average at least 80 °F.
The 112 °F cap is this implementation's support restriction, not a universal
NWS assertion that heat stops being hazardous above 112 °F.

Reference: [NWS equation and screening procedure](https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml).
This value describes shade/light-wind conditions. It is not WBGT, a measure of
workload/acclimatization, an injury probability, or permission to resume work.

| Inputs | Stored heat index | Meaning / presentation guidance |
| --- | --- | --- |
| 63 °F, 60% RH | null | Calculation not applicable in these cool conditions; temperature is still available. |
| 90 °F, 60% RH | about 99.68 °F | Calculated heat index available; preserve source and observation time. |
| 90 °F, missing RH | null | Required humidity input unavailable; do not label this “not applicable.” |
| Missing temperature, 60% RH | null | Required temperature input unavailable. |
| 115 °F, 60% RH | null | Outside this implementation's supported range; do not label cool, safe, or not applicable. |
| 80 °F, 0% RH | null | Fails the NWS initial hot-condition screening average. |
| RH outside 0–100% | rejected | Invalid provider data; collector rejects the affected plant, rather than storing a fabricated value. |

A **null alone does not identify its cause**. Current weather table rows do not
store relative humidity, although the retained source payload does. Do not infer
“not applicable” from every null. A known temperature below 80 °F supports that
label; at hot temperatures, missing humidity versus out-of-range inputs must be
resolved using the retained source evidence or an agreed API representation.
If the API lacks enough information, show “calculation unavailable” honestly.

Machine-readable examples: `get_data/generated/heat-index-cases.json`.
The examples are deterministic calculation fixtures, not live measurements.
Sid supplies these definitions and tested examples. Alan owns response mapping;
Aryan owns both supervisor and crew labels. No shared API field has
been added by this document. Severity, monitoring health, and measurement
availability remain separate concepts. A mandatory alert always takes precedence.
