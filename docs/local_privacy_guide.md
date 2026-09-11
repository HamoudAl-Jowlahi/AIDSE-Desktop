# AIDSE Desktop — End-User Local Privacy Guide

Welcome to **AIDSE Desktop**! AIDSE is designed as a **local-first desktop platform**, giving you complete control over your datasets, machine learning models, and evaluation results.

---

## 🛡️ Our Core Privacy Commitments

### 1. 100% On-Device Data Processing
When you import datasets, train AutoML models with Optuna/XGBoost/LightGBM/CatBoost, generate SHAP feature explanations, or evaluate model accuracy, **everything happens locally on your computer's CPU and GPU**. Your raw datasets are never uploaded to any cloud server or third-party analytics system.

### 2. Encrypted Data at Rest
All projects, dataset versions, data prep steps, and model evaluation metrics are stored in a local SQLite database protected by **AES-256 SQLCipher encryption**. Your encryption key is stored securely in your operating system's native key vault (Windows Credential Manager, macOS Keychain, or Linux Secret Service).

### 3. No Account or Credentials Required
AIDSE Desktop runs completely offline. You do not need to create an account, log in with an email/password, or sign up for a cloud subscription.

### 4. Transparent Control Over Optional Cloud Features
If you choose to use external cloud features—such as evaluating model outputs using an external **LLM Judge** API—you must explicitly enable the feature and provide your own API key. AIDSE clearly alerts you before any prompt or output is sent to an external service.

---

## 📂 Where Is My Data Stored?

By default, AIDSE stores your encrypted database and local dataset files in your user documents folder:
- **Windows**: `C:\Users\<YourUsername>\Documents\AIDSE`
- **macOS**: `/Users/<YourUsername>/Documents/AIDSE`
- **Linux**: `/home/<YourUsername>/Documents/AIDSE`

You can change or move your local workspace folder at any time from **Settings → Workspace Path**.

---

## 🔌 Offline Capability
AIDSE Desktop operates seamlessly without an internet connection ("Airplane Mode"). You can analyze datasets, build machine learning models, and evaluate golden test cases anywhere, anytime.
