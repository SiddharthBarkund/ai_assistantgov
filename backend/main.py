import os
import re
import uuid
import requests
from datetime import datetime
from flask import Flask, request, jsonify, send_file, session
from flask_cors import CORS
from openai import OpenAI
from PyPDF2 import PdfReader
from docx import Document
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ==================================================================================
# 1. GOOGLE GENAI - PRIMARY MODEL (Gemini 1.5 Pro)
# ==================================================================================
try:
    from google import genai
    from google.genai import types

    GOOGLE_GENAI_AVAILABLE = True
    print("✅ New Google GenAI SDK imported")
except ImportError:
    print("❌ Please install: pip install google-genai")
    GOOGLE_GENAI_AVAILABLE = False

# ==================================================================================
# 2.5. DATASET RAG INITIALIZATION (Supabase PRIMARY, Local FAISS FALLBACK)
# ==================================================================================
SUPABASE_RAG_AVAILABLE = False
FAISS_AVAILABLE = False
DATASET_INDEX = None
DATASET_CHUNKS = None
EMBEDDING_MODEL = None

# --- PRIORITY 1: Try Supabase (Cloud Database via REST API) ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY and SUPABASE_URL != "your-supabase-url-here":
    try:
        from sentence_transformers import SentenceTransformer
        import json

        # Test Supabase connection via REST API
        test_headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }
        test_resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/scheme_chunks?select=id&limit=1",
            headers=test_headers,
            timeout=10
        )
        
        if test_resp.status_code == 200:
            print("✅ Supabase connected successfully! (Cloud RAG Mode)")
            print("⏳ Loading embedding model for RAG queries...")
            EMBEDDING_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
            print("✅ Embedding model loaded!")
            SUPABASE_RAG_AVAILABLE = True
        else:
            print(f"⚠️ Supabase connection failed (Status: {test_resp.status_code}). Trying local FAISS...")
        
    except ImportError:
        print("⚠️ sentence-transformers not installed. Trying local FAISS...")
    except Exception as e:
        print(f"⚠️ Supabase connection failed: {e}. Trying local FAISS...")

# --- PRIORITY 2: Fallback to Local FAISS ---
if not SUPABASE_RAG_AVAILABLE:
    try:
        import faiss
        import pickle
        from sentence_transformers import SentenceTransformer
        
        FAISS_AVAILABLE = True
        print("✅ FAISS and SentenceTransformers available for RAG Dataset.")
        
        if os.path.exists("myscheme_faiss_index.bin") and os.path.exists("myscheme_chunks.pkl"):
            DATASET_INDEX = faiss.read_index("myscheme_faiss_index.bin")
            with open("myscheme_chunks.pkl", "rb") as f:
                DATASET_CHUNKS = pickle.load(f)
            print("✅ Dataset FAISS Index loaded successfully! (Local RAG Mode)")
            print("⏳ Loading embedding model for RAG queries...")
            EMBEDDING_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
            print("✅ Dataset Embedding model loaded successfully!")
        else:
            print("⚠️ Dataset index files not found. Run build_dataset_index.py first.")
            
    except ImportError:
        print("⚠️ FAISS/SentenceTransformers not installed. Dataset RAG mode inactive.")
    except Exception as e:
        print(f"⚠️ Error loading RAG Dataset: {e}")

def retrieve_dataset_context(query_text, top_k=3):
    """Retrieve relevant dataset context - tries Local FAISS first for speed, then Supabase Cloud as fallback."""
    
    # --- Method 1: Local FAISS (Primary for Speed) ---
    if FAISS_AVAILABLE and DATASET_INDEX and EMBEDDING_MODEL:
        try:
            query_emb = EMBEDDING_MODEL.encode([query_text]).astype("float32")
            distances, indices = DATASET_INDEX.search(query_emb, top_k)
            
            context_parts = []
            for i in range(top_k):
                idx = indices[0][i]
                if idx != -1 and idx < len(DATASET_CHUNKS):
                    chunk = DATASET_CHUNKS[idx]
                    context_parts.append(f"Source: {chunk['filename']}\nContent: {chunk['text']}")
            
            if context_parts:
                return "\n\n".join(context_parts)
                
        except Exception as e:
            print(f"FAISS RAG search error: {e}")
            # Fall through to Supabase if FAISS fails
    
    # --- Method 2: Supabase (Cloud Fallback) ---
    if SUPABASE_RAG_AVAILABLE and EMBEDDING_MODEL:
        try:
            query_emb = EMBEDDING_MODEL.encode([query_text]).tolist()[0]
            
            headers = {
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json"
            }
            
            # Call the match_scheme_chunks RPC function
            rpc_response = requests.post(
                f"{SUPABASE_URL}/rest/v1/rpc/match_scheme_chunks",
                headers=headers,
                json={
                    "query_embedding": query_emb,
                    "match_count": top_k
                },
                timeout=15
            )
            
            if rpc_response.status_code == 200:
                results = rpc_response.json()
                if results:
                    context_parts = []
                    for row in results:
                        context_parts.append(f"Source: {row['filename']}\nContent: {row['chunk_text']}")
                    return "\n\n".join(context_parts)
                    
        except Exception as e:
            print(f"Supabase RAG search error: {e}")
    
    return ""


# ==================================================================================
# 2.7. REAL-TIME SCRAPER (FALLBACK FOR API QUOTA EXHAUSTED)
# ==================================================================================
def scrape_myscheme(query, lang="en"):
    """
    Scrapes MyScheme.gov.in in real-time when AI APIs are down.
    Returns a formatted string in Sarkar Mitra style.
    """
    try:
        from bs4 import BeautifulSoup
        import json
        
        api_key = os.getenv("MYSCHEME_API_KEY")
        
        # Enhanced headers to mimic a real browser session perfectly
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.myscheme.gov.in/",
            "Origin": "https://www.myscheme.gov.in",
            "x-api-key": api_key,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }

        # --- STEP 0: ADVANCED QUERY CLEANING ---
        clean_query = query.lower()
        fillers = ["tell me about", "what is", "show me", "information on", "scheme for",
                   "yojana for", "about", "list", "schemes", "yojanas", "details of",
                   "give me", "tell me full details about", "full details about",
                   "details info of", "detail info about", "best schema for", "best scheme for"]
        for f in fillers:
            clean_query = clean_query.replace(f, "")
        clean_query = clean_query.strip()
        if not clean_query: clean_query = query

        # Robust Force Detail Mode: Detection
        force_detail = any(x in query.lower() for x in ["full details", "detailed info", "detail of", "tell me about this", "show details"])

        # --- STEP 0.5: SMART CONTEXT / AGE DETECTION ---
        # Detect if user says something like "8 year old girl" or "10 year old boy"
        # and map it to actual search keywords
        import re as _re
        age_match = _re.search(r'(\d+)\s*(?:year|yr|sal|वर्ष|साल)', clean_query)
        detected_age = int(age_match.group(1)) if age_match else None

        # Context-aware keyword injection based on age + gender
        extra_search_terms = []
        if detected_age is not None:
            is_girl  = any(w in clean_query for w in ["girl", "kanya", "ladki", "mulgi", "female", "beti"])
            is_boy   = any(w in clean_query for w in ["boy", "mula", "bal", "beta", "male"])
            is_child = is_girl or is_boy or any(w in clean_query for w in ["child", "baby", "infant", "mulanchi", "baccha"])

            if is_girl and detected_age <= 18:
                extra_search_terms = ["girl child scheme", "kanya yojana", "beti bachao",
                                      "Majhi Kanya Bhagyashree", "Sukanya Samridhi",
                                      "Balika Samridhi Yojana"]
                clean_query = "girl child scheme kanya"
                print(f"🎯 Age-context detected: {detected_age} yr old girl → girl child schemes")
            elif is_boy and detected_age <= 18:
                extra_search_terms = ["bal scheme", "child welfare scheme", "boy education scheme"]
                clean_query = "child welfare boy scheme"
                print(f"🎯 Age-context detected: {detected_age} yr old boy → child schemes")
            elif is_child:
                extra_search_terms = ["child welfare scheme", "bal vikas", "Integrated Child Development"]
                clean_query = "child welfare scheme"
                print(f"🎯 Age-context detected: {detected_age} yr old child → child schemes")

        # --- STEP 1: CATEGORY-SPECIFIC MH PRIORITY (Supabase + Fallback) ---
        MH_PRIORITY_MAP = {}
        try:
            supabase_headers = {
                "apikey": os.getenv("SUPABASE_KEY"),
                "Authorization": f"Bearer {os.getenv('SUPABASE_KEY')}"
            }
            sb_url = f"{os.getenv('SUPABASE_URL')}/rest/v1/mh_priority_schemes?select=category,scheme_name"
            sb_resp = requests.get(sb_url, headers=supabase_headers, timeout=5)
            if sb_resp.status_code == 200:
                for entry in sb_resp.json():
                    MH_PRIORITY_MAP[entry['category'].lower()] = entry['scheme_name']
                print(f"✅ Loaded {len(MH_PRIORITY_MAP)} priority schemes from Supabase.")
        except:
            pass

        if not MH_PRIORITY_MAP:
            MH_PRIORITY_MAP = {
                "farmer": "Mahatma Jyotirao Phule Shetkari Karjamukti Yojana",
                "women": "Majhi Kanya Bhagyashree Yojana",
                "student": "Rajarshi Shahu Maharaj Scholarship",
                "scholarship": "Rajarshi Shahu Maharaj Scholarship",
                "housing": "Ramai Awas Yojana",
                "msme": "Chief Minister Employment Generation Programme",
                "startup": "Chief Minister Employment Generation Programme",
                "health": "Mahatma Jyotiba Phule Jan Arogya Yojana",
                "pension": "Sanjay Gandhi Niradhar Anudan Yojana",
                "skill": "Pandit Deendayal Upadhyay Kaushalya Yojana Maharashtra"
            }

        search_terms = []

        # LOGIC FIX: If user wants DETAILS for X, search ONLY for X.
        if force_detail:
            search_terms.append(clean_query)
        else:
            # Add extra age-context terms FIRST (highest priority)
            if extra_search_terms:
                search_terms.extend(extra_search_terms)
            else:
                # Match category for Pos #1 (Only for broad lists)
                for cat, fixed_name in MH_PRIORITY_MAP.items():
                    if cat in clean_query:
                        search_terms.append(fixed_name)
                        break
            search_terms.append(clean_query)

        if " " in clean_query and not force_detail and not extra_search_terms:
            search_terms.extend(clean_query.split())

        search_results = []
        seen_slugs = set()
        
        for term in search_terms:
            if len(term) < 2: continue
            try:
                # Increased size to 20 to ensure we find enough MH/Central schemes
                search_api_url = f"https://api.myscheme.gov.in/search/v6/schemes?lang={lang}&q=[]&keyword={term}&sort=&from=0&size=20"
                api_resp = requests.get(search_api_url, headers=headers, timeout=10)
                
                if api_resp.status_code == 200:
                    search_data = api_resp.json()
                    hits = search_data.get("data", {}).get("hits", {}).get("items", [])
                    if hits:
                        for hit in hits:
                            slug = (hit.get("fields", {}).get("slug") or hit.get("slug"))
                            if slug and slug not in seen_slugs:
                                search_results.append(hit)
                                seen_slugs.add(slug)
                        # If we found the primary MH scheme, we continue to get more for the list
                        if len(search_results) >= 10: break
            except Exception as e:
                print(f"⚠️ Search API failed for term '{term}': {e}")

        # --- STEP 2: SUPABASE DATASET FALLBACK (If Results < 3) ---
        if len(search_results) < 3:
            print("🔍 API results low, querying Supabase Indian Schemes dataset...")
            try:
                # Detect the main category from search terms or query
                matched_cat = None
                for cat in ["farmer", "women", "student", "housing", "msme", "startup", "health", "pension", "skill"]:
                    if cat in clean_query:
                        matched_cat = cat.capitalize() # Supabase uses Capitalized
                        break
                
                if matched_cat:
                    # Fetch from indian_schemes table
                    sb_url = f"{os.getenv('SUPABASE_URL')}/rest/v1/indian_schemes?category=eq.{matched_cat}&select=scheme_name,state_type&limit=10"
                    sb_headers = {
                        "apikey": os.getenv("SUPABASE_KEY"),
                        "Authorization": f"Bearer {os.getenv('SUPABASE_KEY')}"
                    }
                    sb_resp = requests.get(sb_url, headers=sb_headers, timeout=5)
                    
                    if sb_resp.status_code == 200:
                        db_schemes = sb_resp.json()
                        # Sort DB schemes: MH first
                        db_schemes.sort(key=lambda x: 0 if "maharashtra" in str(x.get('state_type')).lower() else 1)
                        
                        for db_item in db_schemes:
                            db_name = db_item.get('scheme_name')
                            if db_name and db_name not in [s.get('fields', {}).get('schemeName') for s in search_results]:
                                # Try one targeted search for this specific scheme name
                                try:
                                    target_url = f"https://api.myscheme.gov.in/search/v6/schemes?lang={lang}&q=[]&keyword={db_name}&sort=&from=0&size=1"
                                    target_resp = requests.get(target_url, headers=headers, timeout=5)
                                    if target_resp.status_code == 200:
                                        t_hits = target_resp.json().get("data", {}).get("hits", {}).get("items", [])
                                        if t_hits:
                                            hit = t_hits[0]
                                            t_slug = (hit.get("fields", {}).get("slug") or hit.get("slug"))
                                            if t_slug and t_slug not in seen_slugs:
                                                search_results.append(hit)
                                                seen_slugs.add(t_slug)
                                                if len(search_results) >= 5: break
                                except: continue
            except Exception as e:
                print(f"⚠️ Supabase dataset fallback failed: {e}")

        # --- STEP 2: SCRAPING METHOD (ULTIMATE FALLBACK) ---
        if not search_results:
            try:
                search_url = f"https://www.myscheme.gov.in/{lang}/search?query={clean_query}"
                response = requests.get(search_url, headers=headers, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    for a in soup.find_all('a', href=True):
                        href = a['href']
                        if "/schemes/" in href and not any(x in href for x in ["/schemes/state", "/schemes/department"]):
                            slug = href.split('/')[-1]
                            search_results.append({"slug": slug, "schemeName": slug.replace('-', ' ').title()})
                            if len(search_results) >= 5: break
            except:
                pass

        # --- STEP 3: BALANCED MIX SORTING (1 MH -> 1 Central -> 1 Top India) ---
        mh_schemes = []
        central_schemes = []
        other_schemes = []
        
        # --- GLOBAL CATEGORY SMART FILTERS ---
        # name_blocked = HARD reject if any of these words appear in the SCHEME NAME
        # blocked      = reject if found in name OR description
        # allowed      = at least one must be present in name OR description
        CATEGORY_RULES = {
            "farmer": {
                "allowed": ["farmer", "krishi", "agriculture", "crop", "irrigation",
                             "soil", "shetkari", "fertilizer", "livestock", "kisan",
                             "shet", "harvest", "dairy", "poultry", "karjamukti",
                             "tractor", "pump", "waive", "agri", "pashu", "bhu",
                             "jal sanjivani", "krushi", "phule shetkari"],
                "name_blocked": ["mahila", "women", "girl", "female", "kanya",
                                  "samridhi", "shakti", "ladki", "widow", "bachat",
                                  "student", "scholarship", "awas", "housing", "hostel",
                                  "startup", "skill", "pension", "health", "arogya"],
                "blocked": ["student", "scholarship", "startup", "urban",
                             "mahila", "women", "female", "self help group", "shg",
                             "housing", "awas", "pension", "health", "arogya"]
            },
            "women": {
                "allowed": ["women", "girl", "female", "mahila", "kanya",
                             "maternity", "shakti", "widow", "bachat", "ladki",
                             "mother", "lady", "asra", "savitribai", "majhi kanya",
                             "beti", "balika", "sukanya", "mulgi"],
                "name_blocked": ["farmer", "shetkari", "kisan", "krishi",
                                  "startup", "industrial", "student", "scholarship",
                                  "old age", "old age home", "senior", "vruddha",
                                  "vruddhashra", "aged", "elderly", "pension",
                                  "nivrutti", "niradhar", "grant in aid to old",
                                  "shravan", "geriatric"],
                "blocked": ["farmer", "industrial", "startup", "shetkari",
                             "krishi", "student", "scholarship",
                             "old age", "senior citizen", "vruddha", "pension",
                             "niradhar", "shravan", "elderly", "aged home"]
            },
            "student": {
                "allowed": ["student", "scholarship", "scholar", "matric", "ebc",
                             "fee", "stipend", "education", "vidyarthi", "hostel",
                             "book", "coaching", "exam", "university", "college",
                             "degree", "diploma", "shishyavrutti"],
                "name_blocked": ["pension", "housing", "awas", "farmer", "shetkari",
                                  "mahila", "women", "health", "arogya"],
                "blocked": ["pension", "business", "housing", "farmer",
                             "shetkari", "krishi", "mahila", "women", "health"]
            },
            "housing": {
                "allowed": ["housing", "awas", "gharkul", "flat", "home",
                             "construction", "shelter", "house", "plot",
                             "rehabilitation", "shahari", "gramin awas"],
                "name_blocked": ["scholarship", "health", "pension", "farmer",
                                  "mahila", "women", "skill", "student"],
                "blocked": ["scholarship", "health", "pension", "farmer",
                             "krishi", "skill", "student"]
            },
            "health": {
                "allowed": ["health", "medical", "hospital", "treatment", "arogya",
                             "insurance", "ayushman", "disease", "dialysis", "checkup",
                             "medicine", "doctor", "ambulance", "surgery", "jan arogya",
                             "jeevandayee", "swasthya"],
                "name_blocked": ["housing", "scholarship", "startup", "farmer",
                                  "shetkari", "education", "student", "pension",
                                  "skill", "krishi"],
                "blocked": ["housing", "scholarship", "startup", "farming",
                             "education", "student", "degree", "phd",
                             "shetkari", "krishi", "pension", "skill"]
            },
            "pension": {
                "allowed": ["pension", "nivrutti", "old age", "senior citizen",
                             "widow", "disability", "social security", "social justice",
                             "niradhar", "veruddh", "vruddha", "anudan", "shravan bal"],
                "name_blocked": ["student", "education", "startup", "scholarship",
                                  "farmer", "shetkari", "housing", "awas",
                                  "health", "skill", "mahila"],
                "blocked": ["student", "education", "startup", "child",
                             "scholarship", "farmer", "krishi", "housing",
                             "health", "skill"]
            },
            "skill": {
                "allowed": ["skill", "training", "kaushalya", "vocational",
                             "apprenticeship", "employment", "entrepreneurship",
                             "startup", "job", "iti", "rojgar", "pramod mahajan",
                             "ddu-gky", "nsdc"],
                "name_blocked": ["housing", "pension", "medical", "farmer",
                                  "shetkari", "scholarship", "student", "mahila",
                                  "arogya", "health"],
                "blocked": ["housing", "pension", "medical", "farmer",
                             "shetkari", "krishi", "health", "arogya"]
            },
            "msme": {
                "allowed": ["msme", "startup", "entrepreneur", "business", "udyog",
                             "industry", "employment generation", "udyogini",
                             "mudra", "cluster", "technology upgradation"],
                "name_blocked": ["farmer", "shetkari", "student", "scholarship",
                                  "mahila", "pension", "housing", "health"],
                "blocked": ["farmer", "shetkari", "student", "scholarship",
                             "pension", "housing", "health"]
            }
        }

        # Detect active category from query
        active_cat = None
        query_lower = clean_query.lower()
        cat_keywords = {
            "farmer":  ["farmer", "shetkari", "kisan", "krishi", "agriculture", "agri"],
            "women":   ["women", "mahila", "girl", "female"],
            "student": ["student", "scholarship", "vidyarthi", "shishya"],
            "housing": ["housing", "awas", "gharkul", "house"],
            "health":  ["health", "arogya", "medical", "hospital"],
            "pension": ["pension", "nivrutti", "niradhar", "vruddha"],
            "skill":   ["skill", "kaushalya", "vocational", "training"],
            "msme":    ["msme", "startup", "business", "udyog"],
        }
        for cat, kws in cat_keywords.items():
            if any(kw in query_lower for kw in kws):
                active_cat = cat
                break

        for item in search_results:
            fields = item.get("fields", {})
            name = (fields.get("schemeName") or item.get("schemeName") or "").lower()
            desc = (item.get("briefDescription") or fields.get("briefDescription") or "").lower()

            # --- STRICT RELEVANCE VALIDATION ---
            if active_cat and active_cat in CATEGORY_RULES:
                rules = CATEGORY_RULES[active_cat]

                # HARD BLOCK: blocked word in SCHEME NAME → always reject, no exceptions
                name_has_blocked = any(t in name for t in rules.get("name_blocked", []))
                if name_has_blocked:
                    print(f"🚫 HARD REJECT (name block) [{active_cat}]: {name}")
                    continue

                # SOFT CHECK: allowed word must exist in name or desc
                has_allowed = any(t in name or t in desc for t in rules["allowed"])
                # SOFT CHECK: blocked word in name or desc → reject
                has_blocked = any(t in name or t in desc for t in rules["blocked"])

                if not has_allowed or has_blocked:
                    print(f"🚫 Discarding irrelevant [{active_cat}] scheme: {name}")
                    continue

            level_obj = fields.get("level") or item.get("level")
            level_label = level_obj.get("label", "").lower() if isinstance(level_obj, dict) else str(level_obj).lower()
            
            state_list = fields.get('beneficiaryState') or item.get('beneficiaryState') or []
            state_str = str(state_list).lower()
            is_mh = "maharashtra" in state_str or "maharashtra" in str(item).lower()
            
            dept_obj = fields.get("nodalDepartmentName") or item.get("nodalDepartmentName")
            dept_label = dept_obj.get("label", "").lower() if isinstance(dept_obj, dict) else ""
            
            if is_mh or "maharashtra" in dept_label:
                mh_schemes.append(item)
            elif "central" in level_label or "all" in state_str:
                central_schemes.append(item)
            elif "state" in level_label:
                continue # Skip other specific states
            else:
                other_schemes.append(item)

        # Build balanced list: 1 MH, 1 Central, 1 Next Best
        balanced_results = []
        if mh_schemes:
            balanced_results.append(mh_schemes.pop(0))
        if central_schemes:
            balanced_results.append(central_schemes.pop(0))
            
        remaining = mh_schemes + central_schemes + other_schemes
        while len(balanced_results) < 3 and remaining:
            balanced_results.append(remaining.pop(0))

        sorted_results = balanced_results[:3]
        
        # FINAL FALLBACK: If filtering was TOO strict and we have 0 results, 
        # but the original search HAD results, use the unfiltered ones.
        if not sorted_results and search_results:
            print("⚠️ All results filtered out. Relaxing filters for user satisfaction...")
            sorted_results = search_results[:3]

        # --- STEP 4: SMART FORMATTING (BROAD vs SPECIFIC) ---
        if not sorted_results:
            return "🏛️ **Sarkar Mitra Notice:**\n\nI couldn't find any specific matching schemes for your query right now. Please try a different category or a more specific scheme name! 📋"
        is_broad = (len(sorted_results) > 1 and not force_detail) or (any(x in query.lower() for x in ["schemes", "list", "farmer", "student", "women"]) and not force_detail)
        
        if is_broad:
            final_output = "🏛️ **Top Recommended Schemes:**\n\n"
            for idx, item in enumerate(sorted_results):
                fields = item.get("fields", {})
                name = fields.get("schemeName") or item.get("schemeName") or "Government Scheme"
                slug = fields.get("slug") or item.get("slug")
                
                # Better Authority extraction (State-aware)
                dept_obj = fields.get('nodalDepartmentName') or item.get('nodalDepartmentName')
                min_obj = fields.get('nodalMinistryName') or item.get('nodalMinistryName')
                level_obj = fields.get('level') or item.get('level')
                state_list = fields.get('beneficiaryState') or item.get('beneficiaryState') or []
                
                authority = "Government Authority"
                
                # Priority 1: Use specific state name if found
                if state_list and isinstance(state_list, list) and state_list[0] != "All":
                    authority = f"Government of {state_list[0]}"
                # Priority 2: Use Ministry or Department label
                elif isinstance(min_obj, dict) and min_obj.get('label'):
                    authority = min_obj.get('label')
                elif isinstance(dept_obj, dict) and dept_obj.get('label'):
                    authority = dept_obj.get('label')
                
                # Add Central indicator if applicable
                level_label = level_obj.get('label') if isinstance(level_obj, dict) else str(level_obj)
                if level_label == "Central" and "Central" not in authority:
                    if "Government" not in authority:
                        authority = f"Government of India (Central)"
                    else:
                        authority += " (Central)"
                
                # Smart Highlight Extraction (No Truncation, Complete Sentences)
                full_desc = item.get("briefDescription") or fields.get("briefDescription") or "This is an official government initiative for eligible citizens."
                # Split into sentences and pick top 3
                sentences = [s.strip() + "." for s in full_desc.split('.') if len(s.strip()) > 10]
                if not sentences: sentences = [full_desc]
                highlights = sentences[:3] 
                
                final_output += f"**{idx+1}️⃣ {name}**\n"
                final_output += f"A) Launched By: {authority}\n"
                final_output += f"B) Key Highlights:\n"
                for point in highlights:
                    final_output += f"- {point}\n"
                final_output += f"📄 Click here for full details\n\n---\n\n"
            
            closing = {
                "marathi": "💬 कोणत्याही योजनेबद्दल अधिक माहिती हवी असल्यास, मला कधीही विचारा!",
                "hindi": "💬 किसी भी योजना के बारे में अधिक जानकारी चाहिए? बेझिझक पूछें!",
                "english": "💬 Need more info on any scheme? Feel free to ask me anytime!"
            }
            final_output += closing.get(lang, closing["english"])
            return final_output

        # Else: Single Scheme Full Detailed Mode
        fields = sorted_results[0].get("fields", {})
        slug = fields.get("slug") or sorted_results[0].get("slug")
        details_url = f"https://api.myscheme.gov.in/schemes/v6/public/schemes?slug={slug}&lang={lang}"
        
        details_resp = requests.get(details_url, headers=headers, timeout=10)
        if details_resp.status_code != 200:
            return None
            
        json_data = details_resp.json()
        s_data = json_data.get("data", {}).get(lang, {})
        if not s_data: return None
            
        b_details = s_data.get("basicDetails", {})
        name = b_details.get("schemeName", "Government Scheme")
        authority = b_details.get("nodalMinistryName", {}).get("label", "Government of India")
        level = b_details.get("level", {}).get("label", "Central")
        target = ", ".join([t.get("label") for t in b_details.get("targetBeneficiaries", [])])
        
        content = s_data.get("schemeContent", {})

        def parse_content_list(block_list):
            points = []
            for p in block_list:
                text = "".join([c.get("text", "") for c in p.get("children", []) if c.get("text")])
                if text.strip(): points.append(text.strip())
            return points

        # Extracting Sections
        intro_raw = parse_content_list(content.get("detailedDescription", []))
        intro = " ".join(intro_raw[:3]) if intro_raw else "This scheme is an initiative to provide essential support and resources to eligible citizens."
        
        benefits = parse_content_list(content.get("benefits", []))
        eligibility = parse_content_list(content.get("eligibility", []))
        docs = parse_content_list(content.get("documentsRequired", []))
        process = parse_content_list(content.get("applicationProcess", []))
        impact_raw = parse_content_list(s_data.get("successStory", []))
        
        # Fallbacks for empty sections
        if not benefits: benefits = ["Direct financial assistance.", "Access to government resources.", "Empowerment through dedicated support."]
        if not eligibility: eligibility = ["Must be a resident of India.", "Must fall under the target beneficiary group.", "Annual income within specified limits."]
        if not docs: docs = ["Aadhaar Card copy.", "Address proof (Electricity/Water bill).", "Bank account details for DBT."]
        if not process: process = ["Visit the official portal link below.", "Register with Aadhaar and mobile number.", "Fill the application and upload documents."]
        
        impact = " ".join(impact_raw[:2]) if impact_raw else f"This scheme has empowered thousands of beneficiaries by providing critical support, leading to improved socio-economic stability and growth for citizens like you."

        # Building the Detailed Output
        formatted_response = f"📄 Click here for full details\n---\n"
        formatted_response += f"**1️⃣ {name}**\n\n"
        
        formatted_response += f"📖 Introduction:\n{intro}\n\n"
        
        formatted_response += f"⭐ Key Features:\n"
        formatted_response += f"- Official Government of India Initiative.\n"
        formatted_response += f"- Highly transparent and secure digital processing.\n"
        formatted_response += f"- Targeted support for {target or 'eligible citizens'}.\n\n"
        
        formatted_response += f"💰 Benefits:\n"
        for point in benefits[:3]: formatted_response += f"- {point}\n"
        
        formatted_response += f"\n✅ Eligibility:\n"
        for point in eligibility[:3]: formatted_response += f"- {point}\n"
        
        formatted_response += f"\n📄 Documents Required:\n"
        for point in docs[:3]: formatted_response += f"- {point}\n"
        
        formatted_response += f"\n📝 Application Process:\n"
        for point in process[:3]: formatted_response += f"- {point}\n"
        
        formatted_response += f"\n🌟 Impact:\n{impact}\n\n"
        
        formatted_response += f"🌐 Official Website: [Click Here to Visit](https://www.myscheme.gov.in/schemes/{slug})\n\n"
        
        closing = {
            "marathi": "💬 कोणत्याही योजनेबद्दल अधिक माहिती हवी असल्यास, मला कधीही विचारा!",
            "hindi": "💬 किसी भी योजना के बारे में अधिक जानकारी चाहिए? बेझिझक पूछें!",
            "english": "💬 Need more info on any scheme? Feel free to ask me anytime!"
        }
        formatted_response += closing.get(lang, closing["english"])
        
        return formatted_response
    except Exception as e:
        print(f"Strong Scraping error: {e}")
        return None



# ==================================================================================
# 2. OCR & DEPENDENCY INITIALIZATION
# ==================================================================================
OCR_AVAILABLE = False
TESSERACT_INSTALLED = False
PYMUPDF_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image, ImageEnhance, ImageOps

    OCR_AVAILABLE = True

    if os.name == "nt":
        tesseract_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
        for path in tesseract_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                TESSERACT_INSTALLED = True
                print(f"✅ Tesseract found: {path}")
                break

        if not TESSERACT_INSTALLED:
            try:
                pytesseract.get_tesseract_version()
                TESSERACT_INSTALLED = True
                print("✅ Tesseract found in PATH")
            except:
                print("⚠️ Tesseract not found")
    else:
        try:
            pytesseract.get_tesseract_version()
            TESSERACT_INSTALLED = True
            print("✅ Tesseract available")
        except:
            print("⚠️ Tesseract not installed")

except ImportError:
    print("⚠️ pytesseract/PIL not installed")

try:
    import fitz

    PYMUPDF_AVAILABLE = True
    print("✅ PyMuPDF available")
except ImportError:
    print("⚠️ PyMuPDF not installed")

# ==================================================================================
# 3. FLASK APPLICATION SETUP
# ==================================================================================
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "sarkar_mitra_2026_secure_session_key")
CORS(app, supports_credentials=True)

DOCUMENT_STORE = {}

# ==================================================================================
# 4. API CONFIGURATION - THREE PRIORITY SYSTEM
# ==================================================================================

# PRIMARY: Google Gemini 1.5 Pro (REQUIRED)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# SECONDARY: Hugging Face Inference API (OPTIONAL)
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
HF_MODEL_ID = os.getenv("HF_MODEL_ID", "meta-llama/Meta-Llama-3-8B-Instruct")

# THIRD: Groq (FREE & FAST)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Configure Google Gemini 1.5 Pro (PRIMARY)
gemini_client = None
gemini_pro_available = False

if GOOGLE_GENAI_AVAILABLE:
    if GOOGLE_API_KEY:
        try:
            gemini_client = genai.Client(api_key=GOOGLE_API_KEY.strip())
            print("🔍 Auto-detecting available Gemini models...")
            models_list = gemini_client.models.list()
            preferred_models = [
                "models/gemini-2.5-flash",
                "models/gemini-2.5-pro",
                "models/gemini-2.0-flash",
                "models/gemini-exp-1206",
                "models/gemini-flash-latest",
                "models/gemini-pro-latest",
            ]
            working_model = None
            gemini_quota_exceeded = False

            for pref_model in preferred_models:
                try:
                    test_response = gemini_client.models.generate_content(
                        model=pref_model, contents="Test"
                    )
                    working_model = pref_model
                    gemini_pro_available = True
                    gemini_client.working_model = working_model
                    print(f"✅ 1st PRIORITY: Google Gemini ({working_model}) - ACTIVE")
                    break
                except Exception as e:
                    error_str = str(e)
                    if "429" in error_str or "quota" in error_str.lower() or "RESOURCE_EXHAUSTED" in error_str:
                        gemini_quota_exceeded = True
                        break
                    continue
            
            if not working_model and not gemini_quota_exceeded:
                for model in models_list:
                    if "gemini" in model.name.lower():
                        try:
                            test_response = gemini_client.models.generate_content(
                                model=model.name, contents="Test"
                            )
                            working_model = model.name
                            gemini_pro_available = True
                            gemini_client.working_model = working_model
                            print(f"✅ 1st PRIORITY: Google Gemini ({working_model}) - ACTIVE")
                            break
                        except Exception as e:
                            error_str = str(e)
                            if "429" in error_str or "quota" in error_str.lower():
                                gemini_quota_exceeded = True
                                break
                            continue
            if not working_model:
                gemini_pro_available = False
        except Exception as e:
            gemini_client = None

# Configure Hugging Face (SECONDARY)
hf_available = False
if HUGGINGFACE_API_KEY:
    try:
        test_resp = requests.post(
            f"https://router.huggingface.co/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {HUGGINGFACE_API_KEY.strip()}",
                "Content-Type": "application/json",
            },
            json={
                "model": HF_MODEL_ID,
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 8,
            },
            timeout=20,
        )
        if test_resp.ok:
            hf_available = True
            print(f"✅ 2nd PRIORITY: Hugging Face - ACTIVE ({HF_MODEL_ID})")
    except Exception as e:
        pass

# Configure Groq (THIRD)
groq_client = None
groq_available = False
if GROQ_API_KEY:
    try:
        groq_client = OpenAI(
            base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY.strip()
        )
        test_response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=10,
            timeout=15,
        )
        groq_available = True
        print("✅ 3rd PRIORITY: Groq - ACTIVE")
    except Exception as e:
        groq_client = None


# ==================================================================================
# 5. DOCUMENT TEXT EXTRACTION
# ==================================================================================
def extract_text_from_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext == ".pdf":
            try:
                reader = PdfReader(file_path)
                text = ""
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"

                if not text.strip():
                    if OCR_AVAILABLE and TESSERACT_INSTALLED and PYMUPDF_AVAILABLE:
                        doc = fitz.open(file_path)
                        ocr_text = ""
                        for page_num, page in enumerate(doc):
                            try:
                                pix = page.get_pixmap(dpi=300)
                                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                                img = ImageOps.grayscale(img)
                                img = ImageEnhance.Contrast(img).enhance(2.5)
                                img = ImageEnhance.Sharpness(img).enhance(2.0)

                                try:
                                    page_text = pytesseract.image_to_string(img, lang="eng+mar", config="--psm 6")
                                except:
                                    page_text = pytesseract.image_to_string(img, lang="eng", config="--psm 6")

                                ocr_text += f"\n--- Page {page_num + 1} ---\n{page_text}\n"
                            except Exception as page_error:
                                continue
                        if ocr_text.strip():
                            text = ocr_text
                    else:
                        return None, "Cannot perform OCR. Missing libraries."

                if not text.strip():
                    return None, "PDF appears empty"
                return text, None
            except Exception as e:
                return None, f"PDF reading error: {str(e)}"

        elif ext == ".docx":
            try:
                doc = Document(file_path)
                text = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
                if not text.strip():
                    return None, "DOCX file is empty"
                return text, None
            except Exception as e:
                return None, f"DOCX reading error: {str(e)}"

        elif ext == ".txt":
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    text = f.read()
                if not text.strip():
                    return None, "Text file is empty"
                return text, None
            except UnicodeDecodeError:
                try:
                    with open(file_path, "r", encoding="latin-1") as f:
                        text = f.read()
                    return text, None
                except Exception as e:
                    return None, f"Text file encoding error: {str(e)}"
            except Exception as e:
                return None, f"Text file error: {str(e)}"

        elif ext in [".png", ".jpg", ".jpeg", ".gif", ".bmp"]:
            if not (OCR_AVAILABLE and TESSERACT_INSTALLED):
                return None, "OCR libraries not installed"
            try:
                img = Image.open(file_path)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img = ImageOps.grayscale(img)
                img = ImageEnhance.Contrast(img).enhance(2.5)
                img = ImageEnhance.Sharpness(img).enhance(2.0)

                try:
                    text = pytesseract.image_to_string(img, lang="eng+mar", config="--psm 6")
                except:
                    text = pytesseract.image_to_string(img, lang="eng", config="--psm 6")

                if not text.strip():
                    return None, "No readable text found in image"
                return text, None
            except Exception as e:
                return None, f"Image OCR error: {str(e)}"
        else:
            return None, f"Unsupported file type: {ext}"

    except Exception as e:
        return None, f"File processing error: {str(e)}"


# ==================================================================================
# 6. LANGUAGE DETECTION
# ==================================================================================
def detect_language(text):
    marathi_chars = sum(1 for c in text if "\u0900" <= c <= "\u097f")
    total_chars = len([c for c in text if c.isalpha()])

    if total_chars == 0:
        return "english"

    devanagari_percentage = ((marathi_chars / total_chars) * 100 if total_chars > 0 else 0)

    marathi_words = ["आहे", "होते", "काय", "कसे", "कोण", "कुठे", "केव्हा", "मला", "तुम्हाला", "माहिती", "सांगा", "कृपया"]
    marathi_word_count = sum(1 for word in marathi_words if word in text)

    hindi_words = ["है", "हैं", "था", "थे", "क्या", "कैसे", "कौन", "कहाँ", "कब", "मुझे", "आपको", "बताइए", "कृपया"]
    hindi_word_count = sum(1 for word in hindi_words if word in text)

    if devanagari_percentage > 50:
        if marathi_word_count > hindi_word_count:
            return "marathi"
        elif hindi_word_count > marathi_word_count:
            return "hindi"
        else:
            return "marathi"
    elif devanagari_percentage > 10:
        return "mixed"
    else:
        return "english"


# ==================================================================================
# 7. FRAUD DETECTION ANALYZER
# ==================================================================================
def analyze_document_for_fraud(text):
    warnings = []
    dates = re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", text)
    if len(set(dates)) > 1:
        warnings.append("⚠️ Multiple different dates found")
    names = re.findall(r"\b[A-Z][a-z]{2,15}\s[A-Z][a-z]{2,15}\b", text)
    for name in names:
        if re.search(r"(.)\1{2,}", name):
            warnings.append(f"⚠️ Suspicious name pattern: '{name}'")
    legal_keywords = ["signature", "seal", "stamp", "authorized", "certified"]
    found_keywords = [kw for kw in legal_keywords if kw.lower() in text.lower()]
    if len(found_keywords) < 2:
        warnings.append("⚠️ Document may be missing official stamps/signatures")
    if text.count("  ") > len(text) / 50:
        warnings.append("⚠️ Unusual spacing detected")
    return warnings


# ==================================================================================
# 7.5. SARKAR MITRA PROMPT
# ==================================================================================
SARKAR_MITRA_PROMPT = """You are Sarkar Mitra (सरकार मित्र), a friendly, knowledgeable AI Government Assistant for India.
You are like a helpful elder brother or sister who knows everything about Indian government systems, schemes, and processes.

═══════════════════════════════════════════════════════
🎯 YOUR CAPABILITIES — You can answer ALL of these:
═══════════════════════════════════════════════════════

1. 🏛️ GOVERNMENT SCHEMES — Farmer, Women, Student, Housing, Health, Pension, Skill, MSME
2. 📋 GOVERNMENT DOCUMENTS — How to apply, process, documents needed for:
   - Aadhaar Card, PAN Card, Ration Card, Passport, Voter ID
   - Driving Licence, Birth/Death/Caste/Income Certificate
   - Domicile, Marriage Certificate, Property Registration
3. 💬 FRIENDLY CONVERSATION — Greetings, general questions, "how are you" etc.
4. 🇮🇳 GENERAL GOVERNMENT INFO — Any question about Indian government systems, offices, laws, rights
5. 🔍 ELIGIBILITY CHECK — Check if user is eligible for any scheme based on their profile

═══════════════════════════════════════════════════════
💬 PERSONALITY & TONE
═══════════════════════════════════════════════════════

- Speak like a **knowledgeable, friendly elder sibling** (दादा/ताई जैसा).
- **ALWAYS acknowledge** the user's question warmly before answering.
  Examples: "अरे, हा प्रश्न खूप चांगला आहे!", "Good question! Let me explain this simply.", "बिल्कुल सांगतो!"
- Use **simple, clear language** — avoid heavy jargon.
- Be **encouraging and positive** — never make the user feel bad for asking.
- If user makes a spelling mistake (like "addhr" = Aadhaar, "chard" = card) — **understand and answer correctly**, don't correct them rudely.

═══════════════════════════════════════════════════════
📋 HOW TO ANSWER GENERAL GOVERNMENT QUESTIONS
═══════════════════════════════════════════════════════

For questions like "How to apply Aadhaar card", "PAN card process", "Ration card documents":

**Format:**
🖊️ [Document Name] — How to Apply

📌 What is it?
[1-2 line simple explanation]

📋 Documents Required:
- Document 1
- Document 2
- Document 3

📝 Steps to Apply:
1. Step 1
2. Step 2
3. Step 3

🌐 Official Website: [link if known]
💬 [Friendly closing line]

═══════════════════════════════════════════════════════
🏛️ HOW TO ANSWER SCHEME QUERIES
═══════════════════════════════════════════════════════

### 🛑 SCHEME RULES
1. **GENERAL CATEGORY SEARCH:** Show the most popular/relevant schemes immediately — do NOT refuse.
2. **PROFILE-BASED:** When user gives Age, State, Income — filter strictly.
3. **GEOGRAPHY:** Prioritize Maharashtra + Central Government schemes by default.
4. **CATEGORY ACCURACY:**
   - Farmer query → ONLY show agricultural/farming schemes (NOT mahila, student, pension)
   - Women query → ONLY show women/girl schemes (NOT old age, senior citizen, farmer)
   - Student query → ONLY show scholarship/education schemes
   - Never mix categories under any circumstance.

### 🏗️ SCHEME RESPONSE FORMAT

**1️⃣ [Scheme Name]**
A) Launched By: (Authority)
B) Key Highlights:
- [Point 1]
- [Point 2]
- [Point 3]
📄 Click here for full details

---

### FULL DETAILS FORMAT (when user asks for details of a specific scheme)

**[NUMBER_EMOJI] [Scheme Name]**

📖 Introduction:
[2-3 lines about the scheme]

⭐ Key Features:
- Feature 1.
- Feature 2.
- Feature 3.

💰 Benefits:
- Benefit 1.
- Benefit 2.
- Benefit 3.

✅ Eligibility:
- Criteria 1.
- Criteria 2.
- Criteria 3.

📄 Documents Required:
- Document 1.
- Document 2.
- Document 3.

📝 Application Process:
- Step 1.
- Step 2.
- Step 3.

🌟 Impact:
[Impact or success story]

🌐 Official Website: [Click Here to Visit](URL)

═══════════════════════════════════════════════════════
📝 GENERAL FORMATTING RULES
═══════════════════════════════════════════════════════
- **BULLET POINTS:** Every point MUST start with `- ` (dash + space).
- **LANGUAGE:** Always respond in the SAME language the user wrote in (Marathi/Hindi/English/Mixed).
- **SPELLING MISTAKES:** Understand what user means — "addhr chard" = Aadhaar Card, "ration crad" = Ration Card.
- **FULL STOPS:** Every sentence MUST end with a full stop.
- **FRIENDLY CLOSING:** End every scheme list with:
  - Marathi: `💬 कोणत्याही योजना किंवा सरकारी प्रक्रियेबद्दल अधिक माहिती हवी असल्यास, मला विचारा! मी नेहमी मदतीसाठी आहे. 🙏`
  - Hindi: `💬 किसी भी योजना या सरकारी प्रक्रिया के बारे में जानना हो तो बेझिझक पूछें! मैं हमेशा मदद के लिए हूँ. 🙏`
  - English: `💬 Feel free to ask me anything about government schemes or processes! I'm always here to help. 🙏`

"""




# ==================================================================================
# 8. SYSTEM PROMPT BUILDER
# ==================================================================================
def initialize_messages(session_id=None, user_name=None, user_language="english"):
    doc_text = ""
    fraud_warnings = []
    has_document = False

    if session_id and session_id in DOCUMENT_STORE:
        doc_data = DOCUMENT_STORE[session_id]
        doc_text = doc_data.get("text", "")
        fraud_warnings = doc_data.get("fraud_warnings", [])
        has_document = True

    language_instructions = {
        "marathi": "तुम्हाला संपूर्ण उत्तर **फक्त मराठीत** द्यावे लागेल",
        "hindi": "आपको पूरा जवाब **केवल हिंदी में** देना है",
        "english": "You MUST respond completely in English",
        "mixed": "तुम्ही मुख्यतः मराठीत उत्तर द्या, आवश्यक असल्यास इंग्रजी वापरा",
    }

    current_language_instruction = language_instructions.get(
        user_language, language_instructions["english"]
    )

    if has_document:
        system_content = f"""{SARKAR_MITRA_PROMPT}

**YOUR IDENTITY:**
- Your name: Sarkar Mitra (सरकार मित्र)
- User's name: {user_name if user_name else "User"}

**LANGUAGE RULE:**
{current_language_instruction}

═══════════════════════════════════════════════════════════════
🔴 DOCUMENT MODE - ACTIVE
═══════════════════════════════════════════════════════════════

A document has been uploaded by the user.

**IMPORTANT BEHAVIOR RULES (STRICTLY FOLLOW THIS):**

1. **Use document context ONLY if:**
   - The user question is DIRECTLY related to the uploaded document (e.g. assessing eligibility from it).
   - The retrieved document content is relevant.

2. **If the user question is UNRELATED to the document:**
   - **IGNORE the document completely.**
   - Do NOT say "information not found in document".
   - Simply answer the question using general Indian government scheme knowledge.

3. **When using the document:**
   - Quote relevant parts if helpful.
   - Mention "According to the uploaded document..."

4. **FRAUD CHECK:**
   - Perform fraud checks (dates, names, stamps) ONLY if relevant to the user request.

**FRAUD CHECK RESULTS:**
{chr(10).join(fraud_warnings) if fraud_warnings else "✅ No obvious fraud indicators detected"}

═══════════════════════════════════════════════════════════════
📄 DOCUMENT CONTENT
═══════════════════════════════════════════════════════════════

{doc_text[:45000]}

═══════════════════════════════════════════════════════════════
END OF DOCUMENT
═══════════════════════════════════════════════════════════════
"""

    else:
        system_content = f"""{SARKAR_MITRA_PROMPT}

**YOUR IDENTITY:**
- Your name: Sarkar Mitra (सरकार मित्र)
- User's name: {user_name if user_name else "User"}

**LANGUAGE RULE:**
{current_language_instruction}

═══════════════════════════════════════════════════════════════
🟡 CONSULTATION MODE - ACTIVE (No Document)
═══════════════════════════════════════════════════════════════
"""

    return system_content


# ==================================================================================
# 9. FLASK ROUTES
# ==================================================================================

@app.route("/")
def index():
    return jsonify({"message": "Sarkar Mitra API is running. React frontend endpoints available: /chat, /upload, /newchat etc."})


@app.route("/upload", methods=["POST"])
def upload_file():
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        ext = os.path.splitext(file.filename)[1].lower()
        allowed_extensions = [
            ".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".gif", ".bmp",
        ]

        if ext not in allowed_extensions:
            if ext == ".doc":
                return jsonify({"error": "Old .doc format not supported. Please convert to .docx"}), 400
            return jsonify({"error": f"Unsupported file type: {ext}"}), 400

        if "session_id" not in session:
            session["session_id"] = str(uuid.uuid4())

        session_id = session["session_id"]

        upload_dir = os.path.join(os.getcwd(), "uploads")
        os.makedirs(upload_dir, exist_ok=True)

        safe_filename = f"{uuid.uuid4()}_{file.filename}"
        file_path = os.path.join(upload_dir, safe_filename)

        try:
            file.save(file_path)
        except Exception as save_error:
            return jsonify({"error": f"File save error: {str(save_error)}"}), 500

        try:
            text, error_msg = extract_text_from_file(file_path)

            try:
                os.remove(file_path)
            except:
                pass

            if error_msg:
                return jsonify({"error": error_msg}), 400

            if not text or not text.strip():
                return jsonify({"error": "No extractable text found in file"}), 400

            fraud_warnings = analyze_document_for_fraud(text)

            DOCUMENT_STORE[session_id] = {
                "text": text,
                "filename": file.filename,
                "upload_time": datetime.now().isoformat(),
                "fraud_warnings": fraud_warnings,
            }

            user_name = session.get("user_name")
            user_language = session.get("user_language", "english")
            session["messages"] = []
            session["system_instruction"] = initialize_messages(
                session_id=session_id, user_name=user_name, user_language=user_language
            )
            session.modified = True

            return jsonify({
                "message": f"File '{file.filename}' processed successfully",
                "filename": file.filename,
                "text_length": len(text),
                "fraud_warnings": fraud_warnings,
            })

        except Exception as extract_error:
            try:
                os.remove(file_path)
            except:
                pass
            return jsonify({"error": f"Processing error: {str(extract_error)}"}), 500

    except Exception as e:
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500


@app.route("/chat", methods=["POST"])
def chat():
    global gemini_pro_available, hf_available, groq_available

    try:
        if "session_id" not in session:
            session["session_id"] = str(uuid.uuid4())

        session_id = session["session_id"]
        user_name = session.get("user_name")

        data = request.json
        user_message = data.get("message", "").strip()
        selected_language = data.get("language")

        if not user_message:
            return jsonify({"response": "Please enter a message."}), 400

        detected_language = detect_language(user_message)

        if selected_language and selected_language in ["English", "हिंदी", "मराठी"]:
            lang_map = {"English": "english", "हिंदी": "hindi", "मराठी": "marathi"}
            session["user_language"] = lang_map.get(selected_language, "english")
        elif "user_language" not in session or detected_language != "mixed":
            session["user_language"] = detected_language

        user_language = session.get("user_language", "english")

        session["system_instruction"] = initialize_messages(
            session_id=session_id, user_name=user_name, user_language=user_language
        )

        if "messages" not in session:
            session["messages"] = []

        name_match = re.search(
            r"(?:i am|my name is|maz nav|mi|माझे नाव|मी)\s+([a-zA-Zअ-ॲ]+)",
            user_message.lower(),
        )
        if name_match:
            detected_name = name_match.group(1).capitalize()
            ignored_words = ["looking", "searching", "asking", "sarkar", "mitra", "bot", "ai", "आहे", "होते"]

            if detected_name.lower() not in ignored_words:
                session["user_name"] = detected_name
                session.modified = True

        session["messages"].append({"role": "user", "content": user_message})

        if "conversation_history" not in session:
            session["conversation_history"] = []

        history_entry = {
            "id": str(uuid.uuid4()),
            "question": user_message,
            "timestamp": datetime.now().isoformat(),
            "preview": (user_message[:60] + "..." if len(user_message) > 60 else user_message),
            "language": detected_language,
        }

        session["conversation_history"].insert(0, history_entry)

        if len(session["conversation_history"]) > 100:
            session["conversation_history"] = session["conversation_history"][:100]

        bot_response = None
        used_model = None

        # ----------------------------------------------------------------------------------
        # SMART INTENT DETECTION — Only run scraper for actual scheme queries
        # General govt process questions (Aadhaar, PAN, etc.) go directly to LLM
        # ----------------------------------------------------------------------------------
        def is_scheme_query(msg):
            """Returns True only if the user is asking about a government SCHEME/YOJANA."""
            msg_l = msg.lower()

            # Explicit scheme keywords — always a scheme query
            explicit_scheme = ["scheme", "yojana", "योजना", "स्कीम", "योजनेबद्दल",
                               "farmer scheme", "student scheme", "women scheme",
                               "housing scheme", "health scheme", "pension scheme",
                               "skill scheme", "msme scheme", "scholarship",
                               "shetkari", "anudan", "subsidy", "benefit"]
            if any(kw in msg_l for kw in explicit_scheme):
                return True

            # General government PROCESS questions — NOT a scheme query → go to LLM
            general_process = [
                "aadhaar", "aadhar", "adhaar", "adhar", "aadhhar", "addhr", "आधार",
                "pan card", "पॅन कार्ड",
                "ration card", "रेशन कार्ड",
                "passport", "पासपोर्ट",
                "driving licence", "driving license", "ड्रायव्हिंग",
                "voter id", "election card", "मतदान ओळखपत्र",
                "birth certificate", "जन्म दाखला",
                "death certificate", "मृत्यू दाखला",
                "caste certificate", "जात प्रमाणपत्र",
                "income certificate", "उत्पन्न दाखला",
                "domicile", "अधिवास",
                "marriage certificate", "विवाह नोंदणी",
                "property registration", "मालमत्ता नोंदणी",
                "gst registration", "udyam registration",
                "how to apply", "apply kasa", "apply कसे",
                "process for", "documents needed", "documents required",
                "steps to get", "how can i get", "kasa milel",
                "how to get", "kase kadhayche", "kadhayche",
                "registration process", "online apply",
            ]
            if any(kw in msg_l for kw in general_process):
                # Exception: if they also mention scheme/yojana, still treat as scheme
                if not any(kw in msg_l for kw in ["scheme", "yojana", "anudan", "subsidy"]):
                    return False

            # Category keywords without process intent = scheme query
            category_kws = ["farmer", "shetkari", "kisan", "krishi",
                            "women", "mahila", "kanya", "girl child",
                            "student", "scholarship", "vidyarthi",
                            "housing", "awas", "gharkul",
                            "health", "arogya",
                            "pension", "niradhar", "vruddha",
                            "skill", "kaushalya",
                            "msme", "startup", "udyog"]
            if any(kw in msg_l for kw in category_kws):
                return True

            # Default: let LLM handle it
            return False

        # ----------------------------------------------------------------------------------
        # REAL-TIME SCRAPER — Only for scheme queries
        # ----------------------------------------------------------------------------------
        if not bot_response and is_scheme_query(user_message):
            try:
                scrape_lang = "en"
                if user_language == "marathi": scrape_lang = "mr"
                elif user_language == "hindi": scrape_lang = "hi"

                scraped_data = scrape_myscheme(user_message, lang=scrape_lang)

                if scraped_data:
                    bot_response = scraped_data
                    used_model = "REAL-TIME SCRAPER (MyScheme.gov.in)"
                    print("✅ Scraper responded successfully.")
            except Exception as e:
                print(f"⚠️ Scraper failed: {e}")
        elif not bot_response:
            print(f"ℹ️ Non-scheme query → LLM: '{user_message[:60]}'")

        # ----------------------------------------------------------------------------------
        # ORIGINAL AI PRIORITY FLOW (Now acting as Fallbacks during test)
        # ----------------------------------------------------------------------------------

        # 1ST PRIORITY: GEMINI
        if gemini_client and gemini_pro_available and not bot_response:
            try:
                system_instruction = session.get("system_instruction", "")
                
                # Fetch Dataset Context using RAG
                dataset_context = retrieve_dataset_context(user_message)
                
                if dataset_context:
                    rag_prompt = f"""
═══════════════════════════════════════════════════════════════
🟢 DATASET KNOWLEDGE BASE - ACTIVE (Downloaded Dataset)
═══════════════════════════════════════════════════════════════

According to the official downloaded scheme dataset, here is the relevant context:

{dataset_context}

**IMPORTANT BEHAVIOR RULES (DATASET MODE):**
1. Read the dataset context provided above.
2. WARNING: The dataset context might be incomplete (e.g., missing 'Required Documents', 'How to Apply', 'Official Website', etc.). You MUST use your own external AI knowledge / LLM factual database to fill in ALL missing gaps perfectly.
3. You MUST format the output strictly using the 10-point format defined in your SARKAR_MITRA_PROMPT. NEVER skip a section like "Required Documents" or "Official Website". If the dataset doesn't have it, YOU must provide it.
4. ONLY output schemes that verify against either the context or your solid factual understanding. Do not invent schemes.
═══════════════════════════════════════════════════════════════
"""
                    conversation_text = system_instruction + "\n\n" + rag_prompt + "\n\n"
                else:
                    conversation_text = system_instruction + "\n\n"

                for msg in session["messages"]:
                    if msg["role"] == "user":
                        conversation_text += f"User: {msg['content']}\n\n"
                    elif msg["role"] == "assistant":
                        conversation_text += f"Assistant: {msg['content']}\n\n"

                model_name = getattr(gemini_client, "working_model", "gemini-1.5-pro")

                response = gemini_client.models.generate_content(
                    model=model_name, contents=conversation_text
                )
                bot_response = response.text
                used_model = f"1st PRIORITY: Gemini ({model_name}) ⭐"

            except Exception as e:
                error_str = str(e)
                if ("429" in error_str or "quota" in error_str.lower() or "RESOURCE_EXHAUSTED" in error_str):
                    gemini_pro_available = False

        # 2ND PRIORITY: HUGGING FACE
        if hf_available and not bot_response:
            try:
                # Add RAG context for HF as well
                base_sys_instr = session.get("system_instruction", "")
                dataset_context = retrieve_dataset_context(user_message)
                if dataset_context:
                    base_sys_instr += f"\n\nDATASET CONTEXT:\n{dataset_context}\n\nRAG INSTRUCTION: Use dataset context. Complete missing details using AI knowledge. Keep EXACT Sarkar Mitra structure."

                hf_messages = [{"role": "system", "content": base_sys_instr}]
                for msg in session["messages"]:
                    if msg["role"] in ("user", "assistant"):
                        hf_messages.append({"role": msg["role"], "content": msg["content"]})

                hf_resp = requests.post(
                    "https://router.huggingface.co/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {HUGGINGFACE_API_KEY.strip()}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": HF_MODEL_ID,
                        "messages": hf_messages,
                        "max_tokens": 800,
                        "temperature": 0.3,
                    },
                    timeout=60,
                )

                if hf_resp.ok:
                    data = hf_resp.json()
                    generated = None
                    if isinstance(data, dict):
                        choices = data.get("choices") or []
                        if choices:
                            msg = choices[0].get("message") or {}
                            generated = msg.get("content")

                    if not generated:
                        generated = str(data)

                    bot_response = generated.strip()
                    used_model = f"2nd PRIORITY: Hugging Face ({HF_MODEL_ID})"
            except Exception as e:
                pass

        # 3RD PRIORITY: GROQ
        # 3RD PRIORITY: GROQ
        if groq_client and groq_available and not bot_response:
            try:
                openai_messages = [{"role": "system", "content": session.get("system_instruction", "")}] + session["messages"]

                groq_models = ["llama-3.3-70b-versatile", "llama-3.1-70b-versatile", "mixtral-8x7b-32768"]

                for gmodel in groq_models:
                    try:
                        completion = groq_client.chat.completions.create(
                            model=gmodel,
                            messages=openai_messages,
                            temperature=0.3,
                            max_tokens=3000,
                        )
                        bot_response = completion.choices[0].message.content
                        used_model = f"3rd PRIORITY: Groq ({gmodel})"
                        break
                    except:
                        continue
            except Exception as e:
                pass

        # IF ALL FAIL: SYSTEM ERROR FALLBACK
        if not bot_response:
            error_msg = "⚠️ सर्व AI models आणि रिअल-टाइम स्क्रॅपिंग सध्या उपलब्ध नाहीत. कृपया थोड्या वेळाने प्रयत्न करा."
            return jsonify({"response": error_msg}), 503

        session["messages"].append({"role": "assistant", "content": bot_response})
        if len(session["messages"]) > 100:
            session["messages"] = session["messages"][-99:]
        session.modified = True

        return jsonify({"response": bot_response})

    except Exception as e:
        return jsonify({"response": "⚠️ Server error. Please refresh and try again."}), 500


@app.route("/newchat", methods=["POST"])
def new_chat():
    try:
        session_id = session.get("session_id")
        user_name = session.get("user_name")
        user_language = session.get("user_language", "english")

        # Also clear uploaded document if any
        if session_id and session_id in DOCUMENT_STORE:
            del DOCUMENT_STORE[session_id]

        session["messages"] = []
        session["system_instruction"] = initialize_messages(
            session_id=session_id, user_name=user_name, user_language=user_language
        )
        session.modified = True
        return jsonify({"response": "New chat started", "conversations": []})
    except Exception as e:
        return jsonify({"error": "Failed to start new chat"}), 500


@app.route("/conversations", methods=["GET"])
def get_conversations():
    if "messages" not in session:
        return jsonify({"conversations": []})
    return jsonify({"conversations": session["messages"]})


@app.route("/history", methods=["GET"])
def get_history():
    if "conversation_history" not in session:
        session["conversation_history"] = []
    return jsonify({"history": session["conversation_history"]})


@app.route("/clear_document", methods=["POST"])
def clear_document():
    try:
        session_id = session.get("session_id")
        if session_id and session_id in DOCUMENT_STORE:
            del DOCUMENT_STORE[session_id]

        user_name = session.get("user_name")
        user_language = session.get("user_language", "english")
        session["messages"] = []
        session["system_instruction"] = initialize_messages(
            session_id=session_id, user_name=user_name, user_language=user_language
        )
        session.modified = True
        return jsonify({"message": "Document cleared successfully"})
    except Exception as e:
        return jsonify({"error": "Failed to clear document"}), 500


@app.route("/status", methods=["GET"])
def status():
    session_id = session.get("session_id", "None")
    has_document = session_id in DOCUMENT_STORE if session_id else False

    api_status = []
    if gemini_pro_available:
        model_name = getattr(gemini_client, "working_model", "gemini-1.5-pro")
        api_status.append(f"1st: Gemini ({model_name}) ⭐")
    if hf_available:
        api_status.append(f"2nd: Hugging Face ({HF_MODEL_ID}) ✅")
    if groq_available:
        api_status.append("3rd: Groq ⚡")

    if not api_status:
        api_status.append("⚠️ No APIs active")

    user_language = session.get("user_language", "english")
    language_display = {
        "marathi": "मराठी 🇮🇳",
        "hindi": "हिंदी 🇮🇳",
        "english": "English 🇬🇧",
        "mixed": "Mixed",
    }

    return jsonify({
        "status": "online",
        "ocr_available": OCR_AVAILABLE and TESSERACT_INSTALLED,
        "pymupdf_available": PYMUPDF_AVAILABLE,
        "session_id": session_id,
        "document_uploaded": has_document,
        "user_name": session.get("user_name", "Not set"),
        "user_language": language_display.get(user_language, "English"),
        "message_count": len(session.get("messages", [])),
        "available_apis": api_status,
    })


if __name__ == "__main__":
    print("=" * 80)
    print("🚀 SARKAR MITRA API")
    print("=" * 80)
    print(f"✅ Server starting on: http://localhost:8200")
    print("=" * 80)
    app.run(debug=True, port=8200, host="0.0.0.0")

# ================================================================================
# OTHER PYTHON FILES APPENDED BELOW
# ================================================================================



# ========================================
# --- BEGIN: upload_to_supabase.py ---
# ========================================

"""
Upload existing dataset chunks to Supabase
==========================================
This script reads your local myscheme_chunks.pkl file,
generates embeddings, and uploads everything to Supabase
using direct REST API calls (no supabase SDK needed).

Run this ONCE after setting up Supabase tables.
"""

import os
import pickle
import requests
import json
import numpy as np
from dotenv import load_dotenv

load_dotenv()

# =============================================
# Configuration
# =============================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
CHUNKS_PATH = "myscheme_chunks.pkl"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
BATCH_SIZE = 50  # Upload in batches to avoid timeouts


def main():
    # --- Check Supabase credentials ---
    if not SUPABASE_URL or not SUPABASE_KEY or SUPABASE_URL == "your-supabase-url-here":
        print("[ERROR] SUPABASE_URL and SUPABASE_KEY must be set in .env file!")
        print("  Add these lines to your .env file:")
        print("  SUPABASE_URL=https://your-project-id.supabase.co")
        print("  SUPABASE_KEY=your-anon-key-here")
        return

    # --- Import sentence transformers ---
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("[ERROR] sentence-transformers not installed!")
        print("  Run: pip install sentence-transformers")
        return

    # --- Test Supabase connection ---
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

    print("[0/4] Testing Supabase connection...")
    test_resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/scheme_chunks?select=id&limit=1",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        },
        timeout=10
    )
    if test_resp.status_code != 200:
        print(f"[ERROR] Cannot connect to Supabase! Status: {test_resp.status_code}")
        print(f"  Response: {test_resp.text}")
        print()
        print("  Make sure you have:")
        print("  1. Created the 'scheme_chunks' table in Supabase SQL Editor")
        print("  2. Correct SUPABASE_URL and SUPABASE_KEY in .env")
        return
    print("  [OK] Supabase connected!")

    # --- Load local chunks ---
    if not os.path.exists(CHUNKS_PATH):
        print(f"[ERROR] {CHUNKS_PATH} not found!")
        print("  Make sure you have the chunks file in the backend folder.")
        return

    print(f"[1/4] Loading chunks from {CHUNKS_PATH}...")
    with open(CHUNKS_PATH, "rb") as f:
        chunks = pickle.load(f)
    print(f"  Total chunks to upload: {len(chunks)}")

    # --- Load embedding model ---
    print(f"[2/4] Loading embedding model ({EMBEDDING_MODEL_NAME})...")
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    print("  Model loaded successfully!")

    # --- Generate embeddings ---
    print("[3/4] Generating embeddings for all chunks...")
    texts = [chunk["text"] for chunk in chunks]
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=64)
    print(f"  Generated {len(embeddings)} embeddings (dimension: {embeddings.shape[1]})")

    # --- Upload to Supabase via REST API ---
    print(f"[4/4] Uploading to Supabase in batches of {BATCH_SIZE}...")

    total_uploaded = 0
    total_errors = 0
    total_batches = (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(chunks), BATCH_SIZE):
        batch_chunks = chunks[i:i + BATCH_SIZE]
        batch_embeddings = embeddings[i:i + BATCH_SIZE]

        rows = []
        for chunk, embedding in zip(batch_chunks, batch_embeddings):
            rows.append({
                "filename": chunk["filename"],
                "chunk_text": chunk["text"],
                "embedding": embedding.tolist()
            })

        try:
            resp = requests.post(
                f"{SUPABASE_URL}/rest/v1/scheme_chunks",
                headers=headers,
                json=rows,
                timeout=30
            )

            batch_num = (i // BATCH_SIZE) + 1

            if resp.status_code in [200, 201]:
                total_uploaded += len(rows)
                print(f"  Batch {batch_num}/{total_batches}: Uploaded {len(rows)} chunks [OK]")
            else:
                total_errors += len(rows)
                print(f"  Batch {batch_num}/{total_batches}: FAILED - {resp.status_code} - {resp.text[:200]}")

        except Exception as e:
            total_errors += len(rows)
            print(f"  Batch error: {e}")

    print()
    print("=" * 60)
    print("  UPLOAD COMPLETE!")
    print("=" * 60)
    print(f"  Total chunks uploaded: {total_uploaded}")
    if total_errors > 0:
        print(f"  Errors: {total_errors}")
    print()
    print("  You can now use Supabase for RAG search!")
    print("  Local files (myscheme_faiss_index.bin, myscheme_chunks.pkl)")
    print("  are no longer needed for running the project.")
    print()
    print("  NEXT STEP: Run this SQL in Supabase SQL Editor")
    print("  to create the search index for better performance:")
    print()
    print("  CREATE INDEX ON scheme_chunks")
    print("  USING ivfflat (embedding vector_cosine_ops)")
    print("  WITH (lists = 100);")
    print("=" * 60)


if __name__ == "__main__":
    main()


# --- END: upload_to_supabase.py ---



# ========================================
# --- BEGIN: upload_csv_to_supabase.py ---
# ========================================

import csv
import requests
import os
import glob
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates"
}

def upload_csv_files():
    csv_pattern = r"c:\Users\Siddharth\Downloads\indian_schemes_*.csv"
    csv_files = glob.glob(csv_pattern)
    
    if not csv_files:
        print("❌ No CSV files found.")
        return

    target_table = "indian_schemes"
    seen_ids = set()
    total_files = len(csv_files)
    
    print(f"🚀 Starting upload of {total_files} files...")

    for idx, file_path in enumerate(csv_files, 1):
        filename = os.path.basename(file_path)
        print(f"[{idx}/{total_files}] 📖 Reading {filename}...")
        
        records = []
        try:
            with open(file_path, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sid = int(row["Scheme_ID"])
                    if sid in seen_ids: continue
                    seen_ids.add(sid)
                    records.append({
                        "scheme_id": sid,
                        "scheme_name": row["Scheme_Name"],
                        "category": row["Category"],
                        "state_type": row["Type"]
                    })
            
            if not records:
                print(f"   ⚠️ No new records.")
                continue

            print(f"   ⬆️ Uploading {len(records)} unique records...")
            chunk_size = 100 # Batching to be faster
            for i in range(0, len(records), chunk_size):
                chunk = records[i:i + chunk_size]
                resp = requests.post(
                    f"{SUPABASE_URL}/rest/v1/{target_table}",
                    headers=headers,
                    json=chunk,
                    timeout=30
                )
                if resp.status_code not in [200, 201, 204]:
                    print(f"   ❌ Error at {i}: {resp.text}")
                else:
                    print(f"   ✅ Chunk {i//chunk_size + 1} done.")
                        
        except Exception as e:
            print(f"❌ Critical error in {filename}: {e}")
            
    print(f"\n✨ FINISHED! Total unique schemes in database: {len(seen_ids)}")

if __name__ == "__main__":
    upload_csv_files()


# --- END: upload_csv_to_supabase.py ---



# ========================================
# --- BEGIN: test_api.py ---
# ========================================

import requests
import json

def test_api():
    query = "Farmer Schemes"
    lang = "en"
    api_key = os.getenv("MYSCHEME_API_KEY")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://www.myscheme.gov.in/",
        "x-api-key": api_key
    }
    
    # 1. Test Search
    search_api_url = f"https://api.myscheme.gov.in/search/v6/schemes?lang={lang}&q=[]&keyword={query}&sort=&from=0&size=5"
    print(f"Testing Search API: {search_api_url}")
    try:
        resp = requests.get(search_api_url, headers=headers, timeout=10)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            # print(json.dumps(data, indent=2))
            hits = data.get("data", {}).get("hits", {}).get("items", [])
            print(f"Found {len(hits)} hits.")
            if hits:
                for hit in hits:
                    print(f"- {hit.get('schemeName')} slug: {hit.get('slug')}")
                    
                # 2. Test Details for the first hit
                slug = hits[0].get('slug')
                details_url = f"https://api.myscheme.gov.in/schemes/v6/public/schemes?slug={slug}&lang={lang}"
                print(f"\nTesting Details API for slug '{slug}': {details_url}")
                det_resp = requests.get(details_url, headers=headers, timeout=10)
                print(f"Status: {det_resp.status_code}")
                if det_resp.status_code == 200:
                    det_data = det_resp.json()
                    # print(json.dumps(det_data, indent=2))
                    print("Successfully fetched details.")
                else:
                    print(f"Details failed: {det_resp.text}")
        else:
            print(f"Search failed: {resp.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_api()


# --- END: test_api.py ---



# ========================================
# --- BEGIN: seed_mh_schemes.py ---
# ========================================

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


# --- END: seed_mh_schemes.py ---



# ========================================
# --- BEGIN: debug_state.py ---
# ========================================

import requests
import json

def debug_state_extraction():
    query = "skilled youth"
    lang = "en"
    api_key = os.getenv("MYSCHEME_API_KEY")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.myscheme.gov.in/",
        "Origin": "https://www.myscheme.gov.in",
        "x-api-key": api_key,
        "Accept": "application/json, text/plain, */*",
    }
    
    url = f"https://api.myscheme.gov.in/search/v6/schemes?lang={lang}&q=[]&keyword={query}&sort=&from=0&size=2"
    
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        hits = data.get("data", {}).get("hits", {}).get("items", [])
        if hits:
            item = hits[0]
            fields = item.get("fields", {})
            # Print everything in fields slowly
            for k, v in fields.items():
                print(f"{k}: {v}")
    else:
        print(f"Error {resp.status_code}")

if __name__ == "__main__":
    debug_state_extraction()


# --- END: debug_state.py ---



# ========================================
# --- BEGIN: debug_api.py ---
# ========================================

import requests
import json

def debug_search_api():
    query = "farmer"
    lang = "en"
    api_key = os.getenv("MYSCHEME_API_KEY")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.myscheme.gov.in/",
        "Origin": "https://www.myscheme.gov.in",
        "x-api-key": api_key,
        "Accept": "application/json, text/plain, */*",
    }
    
    url = f"https://api.myscheme.gov.in/search/v6/schemes?lang={lang}&q=[]&keyword={query}&sort=&from=0&size=5"
    
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        hits = data.get("data", {}).get("hits", {}).get("items", [])
        if hits:
            item = hits[0]
            print("Fields keys:", item.get("fields", {}).keys())
            fields = item.get("fields", {})
            print("Scheme name (from fields):", fields.get("schemeName"))
            print("Slug (from fields):", fields.get("slug"))
            print("Ministry (from fields):", fields.get("nodalMinistryName", {}).get("label"))
        else:
            print("No hits found.")

if __name__ == "__main__":
    debug_search_api()


# --- END: debug_api.py ---



# ========================================
# --- BEGIN: build_dataset_index.py ---
# ========================================

import os
import pickle
import faiss
import numpy as np
import PyPDF2
from sentence_transformers import SentenceTransformer
import warnings
import fitz  # PyMuPDF

warnings.filterwarnings("ignore")

# Use relative path so it works on any computer
DATASET_PATH = os.path.join("..", "text_data")
INDEX_PATH = "myscheme_faiss_index.bin"
CHUNKS_PATH = "myscheme_chunks.pkl"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

def extract_text(file_path):
    text = ""
    try:
        if file_path.lower().endswith('.pdf'):
            try:
                # Try PyMuPDF first
                doc = fitz.open(file_path)
                for page in doc:
                    text += page.get_text() + "\n"
            except Exception:
                # Fallback to PyPDF2
                reader = PyPDF2.PdfReader(file_path)
                for page in reader.pages:
                    res = page.extract_text()
                    if res:
                        text += res + "\n"
        elif file_path.lower().endswith('.txt'):
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
    return text.strip()

def chunk_text(text, chunk_size=800, overlap=100):
        words = text.split()
        chunks = []
        if len(words) == 0:
            return chunks
        for i in range(0, len(words), chunk_size - overlap):
            chunk = " ".join(words[i:i + chunk_size])
            if len(chunk.strip()) > 50:
                chunks.append(chunk)
        return chunks

def build_index():
    print("Loading embedding model (this may take a moment)...")
    model = SentenceTransformer(EMBEDDING_MODEL)

    all_chunks = []
    
    files = []
    if os.path.exists(DATASET_PATH):
        files = [f for f in os.listdir(DATASET_PATH) if f.lower().endswith(('.pdf', '.txt'))]
        print(f"Found {len(files)} files in dataset directory.")
    else:
        print(f"Directory {DATASET_PATH} not found.")
        return

    # Process files
    for idx, filename in enumerate(files):
        print(f"Processing ({idx+1}/{len(files)}): {filename}")
        file_path = os.path.join(DATASET_PATH, filename)
        text = extract_text(file_path)
        if text:
            # Chunking
            chunks = chunk_text(text, chunk_size=500, overlap=100)
            for chunk in chunks:
                all_chunks.append({
                    "filename": filename,
                    "text": chunk
                })

    if not all_chunks:
        print("No valid text extracted from the dataset.")
        return

    print(f"Total extracted chunks: {len(all_chunks)}. Computing embeddings...")
    texts_to_embed = [item["text"] for item in all_chunks]
    
    embeddings = model.encode(texts_to_embed, show_progress_bar=True)
    embeddings = np.array(embeddings).astype("float32")

    print("Building FAISS index...")
    d = embeddings.shape[1]
    index = faiss.IndexFlatL2(d)
    index.add(embeddings)

    faiss.write_index(index, INDEX_PATH)
    with open(CHUNKS_PATH, 'wb') as f:
        pickle.dump(all_chunks, f)

    print(f"Success! FAISS Index saved to {INDEX_PATH}")
    print(f"Chunks saved to {CHUNKS_PATH}")

if __name__ == "__main__":
    build_index()


# --- END: build_dataset_index.py ---

