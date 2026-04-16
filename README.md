# 🚀 NovaMind AI Content Pipeline

An end-to-end AI-powered marketing analytics pipeline that automates content generation, audience segmentation, A/B testing, CRM logging, and performance analysis in a single Streamlit application.

---

## 🎯 Business Problem

Early-stage B2B teams struggle to scale content marketing effectively:

- Content creation is manual and slow  
- Messaging is not tailored to different audience segments  
- A/B testing is inconsistent or missing  
- Performance insights are fragmented and delayed  

---

## 💡 Solution

This project simulates a fully automated growth analytics pipeline that:

- Generates blog content and persona-specific newsletters using AI  
- Segments users into personas (Founder, Operations, Marketing)  
- Assigns A/B variants with different messaging strategies  
- Tracks engagement metrics (open, click, conversion)  
- Analyzes results to identify the best-performing strategy  

---

## 📈 What This Pipeline Produces

Each run generates:

- Campaign-level metrics (open rate, CTR, conversion rate)
- Funnel analysis (sent → opened → clicked → converted)
- A/B comparison across personas and variants
- Automated performance summary and next-step recommendation

---

## 🏗️ Architecture Overview

The repository is organized as a modular pipeline.

- app.py orchestrates the full workflow and renders the Streamlit dashboard  
- content_generator.py generates blog content and persona-specific newsletter variants  
- campaign_manager.py segments users and assigns A/B variants  
- crm_hubspot.py handles HubSpot integration (live or simulated)  
- metrics_simulator.py simulates engagement and aggregates metrics  
- performance_analyzer.py generates A/B insights and summaries  
- utils.py provides shared helpers  

---

## 🔄 Flow Diagram

Topic Input → Content Generation → Persona Segmentation → A/B Assignment → CRM Logging → Metrics Simulation → Aggregation & Analysis → Dashboard & Report

---

## 🛠️ Tools, APIs, and Models Used

- Python, Streamlit, Pandas  
- OpenAI API (gpt-4.1-mini)  
- HubSpot CRM API  

---

## ⚠️ Assumptions Made

- Contacts are simulated  
- Email delivery is simulated  
- Metrics are probabilistic  
- No statistical significance testing  
- Designed for demonstration  

---

## ▶️ Instructions to Run Locally

> The app can run fully in mock mode without API keys.
> If you want to use real APIs, add the following to your .env file:
> OPENAI_API_KEY=your_key_here
> HUBSPOT_ACCESS_TOKEN=your_token_here

```bash
# 1. Clone the repository
git clone https://github.com/elinxxy1307-cloud/novamind-ai-marketing-content-pipeline.git
cd novamind-ai-marketing-content-pipeline

# 2. (Optional but recommended) Create a virtual environment
python3 -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env

# 5. Run the app
streamlit run app.py
Open your browser and go to: http://localhost:8501
