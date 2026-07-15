# Known Limitations and Roadmap

---

## Data maturity notice

CCS well integrity is a relatively new discipline. As of 2026 the global CCS injection fleet numbers fewer than 50 commercial-scale wells, with CO₂ injection history spanning at most ~30 years (Sleipner, 1996). No CCS-specific equivalent of OREDA exists. No publicly available CCS-only MTTF database has been published.

All component MTTF values in this model are derived from hydrocarbon-service analogues (OREDA, Peloton WellMaster, SPE papers on acid gas injection) adjusted by expert judgement or drawn from pilot-scale operational experience. They are structured working estimates, not validated engineering data, and should be progressively replaced by field observations as CCS operations mature. The calibration score of ~38/100 (Pre-FEED) in the Model QA tab accurately reflects this state of knowledge.

---

## Current limitations

1. **No component renewal after repair** — a repaired component restarts with the same MTTF distribution as a new one (repair-to-as-new). A repair-to-as-old distinction would improve late-life accuracy.

2. **No rig availability constraint** — the scheduler does not cap simultaneous campaigns by rig count or vessel availability.

3. **Single deferred injection rate** — all deferred rig workovers are penalised at the same daily rate regardless of well productivity.

4. **No spatial or cluster logic** — all wells are treated as independent. Geographic clustering of campaigns is not modelled.

5. **Exponential (memoryless) failure model within phases** — the bathtub curve captures phase-level hazard change but the exponential model within each phase has no memory. Weibull shape parameter is not yet implemented.

6. **Low calibration score (~38/100)** — several high-sensitivity parameters (cement P90 MTTF, packer P90 MTTF, injectivity P90 MTTF, intervention threshold) rely on expert judgement or synthetic assumptions with no direct CCS field data. OREDA-based MTTF values cover hydrocarbon service — no equivalent reliability database exists for CO₂ injection wells. API 6A, API 14A, and NORSOK D-010 are design qualification standards, not operational failure rate databases. Outputs should be treated as order-of-magnitude planning estimates, not engineering commitments. The Model QA tab shows the full breakdown; the Field Calibration tab shows how observed field data progressively replaces literature assumptions.

7. **Joule-Thomson cooling not explicitly modelled** — CO₂ depressurisation during well control events causes extreme cooling (Joule-Thomson effect), which is a CCS-specific failure driver for TRSV, SSV, and packers not present in hydrocarbon service. This mechanism is currently absorbed into the conservative MTTF assumptions rather than modelled as a distinct failure mode.

8. **Thermal/pressure cycling degradation not captured** — cyclical CO₂ injection (on-off supply, workovers, ship unloading intervals) causes progressive cement debonding, casing fatigue, and elastomer creep beyond what the bathtub wear-out ramp captures. CCS operational experience indicates that integrity issues can emerge relatively quickly when wells operate outside their design envelope — consistent with the infant mortality window (years 1–2, 1.5× bathtub multiplier) but with long-term cyclic accumulation not explicitly captured. A future cyclic-fatigue degradation model would improve late-life cement and packer accuracy.

9. **Legacy well conversion risk not fully captured** — the PMC10407664 JPN-1 case study (Indonesia) found that a 10-year-idle well required mandatory re-completion even after a full workover: corrosion rate exceeded 2 mm/yr, existing casing was incompatible with CO₂, and acoustic CBL tools failed to detect the micro-annulus (temperature logging found 2 leaks at 440 m and 881 m that CBL missed). The **Legacy Well Conversion** scenario (2.5× failure multiplier, 1.4× cost multiplier, SCSSV disabled) approximates this risk profile; however, idle-period degradation and material incompatibility are absorbed into the MTTF distribution rather than modelled mechanistically. The 2.5× multiplier captures the worst-case inadequately-assessed-history population; CCS operational experience also shows that well-assessed legacy wells with confirmed good cement and compatible materials can be repurposed with limited intervention, so the multiplier should not be applied uniformly to all legacy wells in a portfolio. The `start_age` fleet age mix (see #11) now captures the structural bathtub-position part of legacy risk separately: a well-assessed, re-completed conversion can be modelled with the age offset alone, reserving the scenario multiplier for the residual material-incompatibility and unknown-history risk.

11. **Fleet age mix is a two-class approximation** *(partially resolved)* — the `start_age` offset ([issue #5](https://github.com/djimrastephane/ccs-workover-forecast/issues/5)) now models converted legacy wells: the **Fleet age mix** sidebar controls assign a fraction of the fleet a starting age on the bathtub curve, so converted wells skip infant mortality and enter the wear-out ramp early (capped at 1.8× beyond design life). Mixed fleets of new and converted wells are supported in a single run, and the Well Journey and Simulation Trace tabs report per-well `start_age` and effective well age. Remaining gaps: (a) the fleet is limited to two age classes (new + one legacy age) rather than a per-well-class table; (b) accumulated physical degradation (corrosion wall loss, cement carbonation, elastomer creep) is not carried forward — the age offset shifts the hazard curve but the MTTF distribution is unchanged; (c) variable conversion quality is still represented only by combining the age offset with the Legacy Well Conversion scenario multiplier rather than per-well assessment scores.

10. **SPE-232388-MS MTTF values are illustrative only and calibrated for a no-bathtub model** — SPE-232388-MS (Table 1) explicitly states: *"The MTTF values utilized in this study are for the sole purpose of validating the model and testing the stochastic framework… these values are illustrative only and should not be used as references or design bases for specific CCS projects."* The SPE model also explicitly excludes the bathtub curve, assuming commissioning eliminates infant mortality and MMV surveillance catches wear-out before functional failure — leaving only the constant-rate useful-life phase. This tool applies a bathtub curve multiplier (1.5× infant mortality; 1.0× useful life; up to 1.8× wear-out) on top of those useful-life-only MTTF values, introducing a systematic conservative bias of approximately 6% over a 30-year simulation relative to SPE's own predictions with the same inputs. Peloton WellMaster AFR values (Hardiman et al. 2023 Note C) are lifecycle-averaged observed rates and are a more coherent input for a bathtub-curve model. SPE Table 1 values are retained as secondary cross-checks and for CO₂-specific failure modes (packer elastomers) where WellMaster HC-service data is known to understate risk.

---

## Recommended next improvements

1. Add Weibull shape parameter to capture intra-phase increasing hazard.
2. Add a rig fleet capacity constraint to cap simultaneous campaigns.
3. Add per-well repair history to adjust future MTTF based on cumulative failure count.
4. Enable CSV upload in the Assumptions tab for project-specific calibration without file editing.
5. Expand `observed_events.csv` with additional CCS field data as it becomes available — the field calibration engine will automatically update MTTF assumptions as confidence grows.
6. Add a legacy-well module to model remediation campaigns for pre-existing O&G wellbores within the storage licence area.
7. Implement a cyclic-fatigue multiplier on cement and elastomeric seals to reflect injection pressure cycling over multi-decade operation.
