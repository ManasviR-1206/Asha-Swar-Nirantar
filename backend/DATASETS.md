# Synthetic Healthcare Datasets & Population Reference Documentation
## ASHA Swar Nirantar — Field Register Data Architecture

### 1. Overview and Privacy Guarantee
All individual beneficiary records, clinical measurements, family structures, and visit timelines generated in ASHA Swar Nirantar are **100% SYNTHETIC DEMO DATA**. No real patient Protected Health Information (PHI) or Aadhaar numbers are stored or processed.

QR identifiers (`ASN-xxxx-xxxx` and `HN-xxxx-xxxx`) are generated using non-sensitive random alphanumeric strings for prototype demonstration.

---

### 2. External Dataset Sources & Benchmarks

The demographic distributions, clinical parameter intervals, and household sanitation metrics in ASHA Swar Nirantar were shaped using references from the following official healthcare benchmarks:

#### Dataset 1: Synthea™ (Synthetic Mass)
- **Source**: [https://synthetichealth.github.io/synthea/](https://synthetichealth.github.io/synthea/)
- **Repository**: [https://github.com/synthetichealth/synthea](https://github.com/synthetichealth/synthea)
- **Licence**: Apache License 2.0
- **Use in ASHA Swar Nirantar**:
  - Longitudinal encounter timelines, clinical observation structures (FHIR/CSV models).
  - Immunisation schedule transitions and pediatric growth curves.

#### Dataset 2: National Family Health Survey (NFHS-5, 2019-21)
- **Source**: [https://data.opencity.in/dataset/national-family-health-survey-nfhs-5-2019-21](https://data.opencity.in/dataset/national-family-health-survey-nfhs-5-2019-21) / [IIPS](http://rchiips.org/nfhs/)
- **Licence**: Open Government Data (OGD) Licence India / Public aggregate survey
- **Use in ASHA Swar Nirantar**:
  - Contextual parameters for Karnataka rural maternal health (ANC intervals, gestational age at first registration, haemoglobin distribution, IFA adherence).
  - Baseline distribution of institutional vs home visits and neonatal checkup timing.
  - Used strictly for population-level statistical context; never for autonomous clinical diagnoses.

#### Dataset 3: Longitudinal Ageing Study in India (LASI, Wave 1)
- **Source**: [https://www.iipsdata.ac.in/datacatalog_detail/5LASI-data](https://www.iipsdata.ac.in/datacatalog_detail/5LASI-data)
- **Licence**: IIPS Data Access Protocol / Academic Research Access
- **Use in ASHA Swar Nirantar**:
  - Elderly chronic care patterns (blood pressure distributions, diabetes screening indicators, functional mobility markers).

#### Dataset 4: Swachh Bharat Mission — Gramin (SBM-G)
- **Source**: [https://www.data.gov.in/catalog/daily-data-rural-sanitation-coverage-under-swachh-bharat-mission](https://www.data.gov.in/catalog/daily-data-rural-sanitation-coverage-under-swachh-bharat-mission)
- **Licence**: Open Government Data (OGD) Licence India
- **Use in ASHA Swar Nirantar**:
  - Household sanitation categories: Individual Household Latrine (IHHL) availability, functional toilet usage, solid waste disposal methods, and village open-defecation-free (ODF) tracking.

#### Dataset 5: Jal Jeevan Mission (JJM)
- **Source**: [https://jaljeevanmission.gov.in/](https://jaljeevanmission.gov.in/)
- **Licence**: Government of India, Ministry of Jal Shakti
- **Use in ASHA Swar Nirantar**:
  - Rural drinking water source categories: functional tap connection (FHTC), piped water supply, borewell with covered vs uncovered storage, drainage condition, and stagnant water monitoring.

---

### 3. Generated Synthetic Dataset Metrics (Current Seed)
- **Fictional Beneficiaries**: 161 (Target >= 150)
  - Pregnant Women: 40+ (8 to 38 weeks gestation)
  - Newborns: 25+ (0 to 28 days old)
  - Children (1–5 years): 40+ (with BCG, OPV, PENTA 1-3, MR vaccination records)
  - Elderly: 20+ (with blood pressure and blood sugar monitoring)
  - Adolescents / General / Nutrition: 25+
- **Fictional Households**: 53 (Target >= 50)
  - Villages: Rampur, Kishanganj, Devgarh, Hoskote, Devanahalli, Chikkaballapur, Kolar, Sidlaghatta, Anekal, Magadi.
  - Household Members: 146 linked members
  - Drinking water source & toilet tracking
- **Longitudinal Visits Recorded**: 165 beneficiary visits + 30 household hygiene visits
- **Follow-ups Scheduled**: 192 (active, upcoming, and overdue for Pulse Drift demonstration)
