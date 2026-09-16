import requests
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

schemes_data = [
    # Farmer Schemes
    {"category": "Farmer", "scheme_name": "Mahatma Jyotirao Phule Shetkari Karjamukti Yojana"},
    {"category": "Farmer", "scheme_name": "Krushi Sinchan Yojana Maharashtra"},
    {"category": "Farmer", "scheme_name": "Nanaji Deshmukh Krishi Sanjivani Yojana"},
    {"category": "Farmer", "scheme_name": "Gopinath Munde Shetkari Apghat Vima Yojana"},
    {"category": "Farmer", "scheme_name": "Dr. Punjabrao Deshmukh Krishi Pump Yojana"},
    {"category": "Farmer", "scheme_name": "Magel Tyala Shet Tale Yojana"},
    {"category": "Farmer", "scheme_name": "Baliraja Jal Sanjivani Yojana"},
    {"category": "Farmer", "scheme_name": "Krishi Yantrikikaran Yojana Maharashtra"},
    {"category": "Farmer", "scheme_name": "Mukhyamantri Krishi Saur Pump Yojana"},
    {"category": "Farmer", "scheme_name": "Bhavantar Yojana Maharashtra"},
    
    # Women Schemes
    {"category": "Women", "scheme_name": "Majhi Kanya Bhagyashree Yojana"},
    {"category": "Women", "scheme_name": "Savitribai Phule Kanya Kalyan Yojana"},
    {"category": "Women", "scheme_name": "Mahila Arthik Vikas Mahamandal Yojana"},
    {"category": "Women", "scheme_name": "Lek Ladki Yojana Maharashtra"},
    {"category": "Women", "scheme_name": "Mahila Udyogini Yojana Maharashtra"},
    {"category": "Women", "scheme_name": "Beti Bachao Beti Padhao Maharashtra Implementation"},
    {"category": "Women", "scheme_name": "Mahila Samman Yojana Maharashtra"},
    {"category": "Women", "scheme_name": "Sakhi One Stop Centre Scheme Maharashtra"},
    {"category": "Women", "scheme_name": "Working Women Hostel Scheme Maharashtra"},
    {"category": "Women", "scheme_name": "Mahila Shakti Kendra Maharashtra"},
    
    # Student Scholarships
    {"category": "Student", "scheme_name": "Rajarshi Shahu Maharaj Scholarship"},
    {"category": "Student", "scheme_name": "EBC Scholarship Maharashtra"},
    {"category": "Student", "scheme_name": "Post Matric Scholarship Maharashtra"},
    {"category": "Student", "scheme_name": "Pre Matric Scholarship Maharashtra"},
    {"category": "Student", "scheme_name": "Dr Panjabrao Deshmukh Hostel Maintenance Allowance"},
    {"category": "Student", "scheme_name": "Minority Scholarship Maharashtra"},
    {"category": "Student", "scheme_name": "OBC Scholarship Maharashtra"},
    {"category": "Student", "scheme_name": "SC Scholarship Maharashtra"},
    {"category": "Student", "scheme_name": "ST Scholarship Maharashtra"},
    {"category": "Student", "scheme_name": "Vocational Education Scholarship Maharashtra"},
    
    # Housing Schemes
    {"category": "Housing", "scheme_name": "Ramai Awas Yojana"},
    {"category": "Housing", "scheme_name": "Shabari Awas Yojana"},
    {"category": "Housing", "scheme_name": "Indira Awas Yojana Maharashtra"},
    {"category": "Housing", "scheme_name": "Pradhan Mantri Awas Yojana Maharashtra"},
    {"category": "Housing", "scheme_name": "Pandit Deendayal Awas Yojana Maharashtra"},
    {"category": "Housing", "scheme_name": "Gharkul Yojana Maharashtra"},
    {"category": "Housing", "scheme_name": "CIDCO Housing Scheme Maharashtra"},
    {"category": "Housing", "scheme_name": "MHADA Lottery Housing Scheme"},
    {"category": "Housing", "scheme_name": "Slum Rehabilitation Authority Scheme Maharashtra"},
    {"category": "Housing", "scheme_name": "Affordable Housing Scheme Maharashtra"},
    
    # MSME & Startup
    {"category": "MSME", "scheme_name": "Chief Minister Employment Generation Programme"},
    {"category": "MSME", "scheme_name": "Udyogini Scheme Maharashtra"},
    {"category": "MSME", "scheme_name": "Prime Minister Employment Generation Programme Maharashtra"},
    {"category": "MSME", "scheme_name": "MSME Subsidy Scheme Maharashtra"},
    {"category": "MSME", "scheme_name": "Startup Maharashtra Policy"},
    {"category": "MSME", "scheme_name": "Maharashtra Industrial Policy"},
    {"category": "MSME", "scheme_name": "Cluster Development Programme Maharashtra"},
    {"category": "MSME", "scheme_name": "Seed Capital Scheme Maharashtra"},
    {"category": "MSME", "scheme_name": "Technology Upgradation Scheme Maharashtra"},
    {"category": "MSME", "scheme_name": "Stand Up India Maharashtra Implementation"},
    
    # Health Schemes
    {"category": "Health", "scheme_name": "Mahatma Jyotiba Phule Jan Arogya Yojana"},
    {"category": "Health", "scheme_name": "Balasaheb Thackeray Arogya Yojana"},
    {"category": "Health", "scheme_name": "Rajiv Gandhi Jeevandayee Arogya Yojana"},
    {"category": "Health", "scheme_name": "Ayushman Bharat Maharashtra Implementation"},
    {"category": "Health", "scheme_name": "National Health Mission Maharashtra"},
    {"category": "Health", "scheme_name": "Janani Suraksha Yojana Maharashtra"},
    {"category": "Health", "scheme_name": "Mukhyamantri Aarogya Mitra Yojana"},
    {"category": "Health", "scheme_name": "Free Dialysis Scheme Maharashtra"},
    {"category": "Health", "scheme_name": "Cancer Care Scheme Maharashtra"},
    {"category": "Health", "scheme_name": "Mobile Medical Unit Scheme Maharashtra"},
    
    # Pension Schemes
    {"category": "Pension", "scheme_name": "Sanjay Gandhi Niradhar Anudan Yojana"},
    {"category": "Pension", "scheme_name": "Shravan Bal Seva Rajya Nivrutti Yojana"},
    {"category": "Pension", "scheme_name": "Indira Gandhi National Old Age Pension Maharashtra"},
    {"category": "Pension", "scheme_name": "Indira Gandhi Widow Pension Scheme Maharashtra"},
    {"category": "Pension", "scheme_name": "Indira Gandhi Disability Pension Scheme Maharashtra"},
    {"category": "Pension", "scheme_name": "Farmer Pension Scheme Maharashtra"},
    {"category": "Pension", "scheme_name": "Destitute Pension Scheme Maharashtra"},
    {"category": "Pension", "scheme_name": "Senior Citizen Pension Maharashtra"},
    {"category": "Pension", "scheme_name": "Handicap Pension Scheme Maharashtra"},
    {"category": "Pension", "scheme_name": "Social Security Pension Maharashtra"},
    
    # Skill Development
    {"category": "Skill", "scheme_name": "Pandit Deendayal Upadhyay Kaushalya Yojana Maharashtra"},
    {"category": "Skill", "scheme_name": "Maharashtra Skill Development Mission"},
    {"category": "Skill", "scheme_name": "Pramod Mahajan Kaushalya Yojana"},
    {"category": "Skill", "scheme_name": "DDU-GKY Maharashtra"},
    {"category": "Skill", "scheme_name": "Skill India Maharashtra Implementation"},
    {"category": "Skill", "scheme_name": "Vocational Training Scheme Maharashtra"},
    {"category": "Skill", "scheme_name": "Apprenticeship Scheme Maharashtra"},
    {"category": "Skill", "scheme_name": "Digital Skill Training Maharashtra"},
    {"category": "Skill", "scheme_name": "Employment Skill Training Scheme Maharashtra"},
    {"category": "Skill", "scheme_name": "Rural Skill Development Scheme Maharashtra"}
]

def insert_data():
    target_table = "mh_priority_schemes"
    print(f"🚀 Attempting to insert 80 schemes into Supabase table: {target_table}...")
    
    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/{target_table}",
        headers=headers,
        json=schemes_data
    )
    
    if resp.status_code in [200, 201]:
        print("✅ Success! All 80 schemes inserted successfully.")
    else:
        print(f"❌ Failed to insert data. Status: {resp.status_code}")
        print(f"Response: {resp.text}")
        print("\n💡 Tip: Make sure you have created the table 'mh_priority_schemes' in Supabase with columns 'category' (text) and 'scheme_name' (text).")

if __name__ == "__main__":
    insert_data()
