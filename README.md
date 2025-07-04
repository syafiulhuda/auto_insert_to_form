# 📘 Project Setup Guide

Panduan singkat untuk menyiapkan environment, source, dan konfigurasi untuk menjalankan program.

---

## 🔧 Program Setup

1. **Aktifkan Virtual Environment:**
   ```bash
   venv\Scripts\activate

2. **Install Dependencies:**
    ```bash
    pip install -r req.txt

3. **Isi Nama Table / List Extractor di Source:**
    - list_batch.txt --> BATCH
    - list_ext_report.txt --> EXT.REPORT
    - list_dfe_parameter.txt --> DFE.PARAMETER
    - list_dfe_mapping.txt --> DFE.MAPPING

4. **Konfigurasi T24:**
    url = T24_url
    username = your_username
    password = your_password

5. **Unidentify Extractor:**
    - Extractor unmatched vs STANDARD.SELECTION disimpan di:
        - inspect/extractor_unidentify.txt