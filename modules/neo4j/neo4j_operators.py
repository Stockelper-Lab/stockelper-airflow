# dags/operators/neo4j_operators.py
"""
Airflow-compatible operators for Neo4j Knowledge Graph ETL using Neo4jHook.
"""

import json
from airflow.exceptions import AirflowSkipException
from airflow.providers.neo4j.hooks.neo4j import Neo4jHook
from typing import Dict, List
import requests

# --- Operator 1: Create Base KG Data (Idempotent) --- #


def create_base_kg_data(neo4j_conn_id: str):
    """
    Populates Neo4j with foundational data. Skips if already completed.
    """
    print("--- Starting Task: create_base_kg_data ---")
    hook = Neo4jHook(neo4j_conn_id)

    # 1. Check if setup is already complete
    setup_check_query = (
        "MATCH (m:Meta {name: 'kg_setup_status', complete: true}) RETURN m"
    )
    setup_status = hook.run(setup_check_query)
    if setup_status:
        print("✓ KG setup is already complete. Skipping task.")
        raise AirflowSkipException("KG setup is already complete.")

    print("\n[1/3] KG setup not found. Proceeding with initial setup...")
    print("\n[2/3] Creating constraints and indexes...")
    # ... (The rest of the function remains the same)
    constraints = [
        "CREATE CONSTRAINT company_code IF NOT EXISTS FOR (c:Company) REQUIRE c.corp_code IS UNIQUE",
        "CREATE CONSTRAINT event_id IF NOT EXISTS FOR (e:Event) REQUIRE e.event_id IS UNIQUE",
        "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.rcept_no IS UNIQUE",
        "CREATE CONSTRAINT person_name IF NOT EXISTS FOR (p:Person) REQUIRE p.name_ko IS UNIQUE",
        "CREATE CONSTRAINT product_id IF NOT EXISTS FOR (p:Product) REQUIRE p.product_id IS UNIQUE",
        "CREATE CONSTRAINT facility_id IF NOT EXISTS FOR (f:Facility) REQUIRE f.facility_id IS UNIQUE",
    ]
    indexes = [
        "CREATE INDEX company_name IF NOT EXISTS FOR (c:Company) ON (c.corp_name)",
        "CREATE INDEX stock_code IF NOT EXISTS FOR (c:Company) ON (c.stock_code)",
    ]

    for c in constraints + indexes:
        try:
            hook.run(c)
            print(f"✓ Executed: {c[:40]}...")
        except Exception as e:
            print(f"✗ Failed to execute schema query: {e}")
            raise

    print("\n[3/3] Creating company data...")
    companies = [
        {
            "corp_code": "00126380",
            "corp_name": "삼성전자",
            "corp_name_eng": "Samsung Electronics",
            "stock_code": "005930",
            "induty_code": "264",
            "corp_cls": "Y",
            "capital_stock": 8970000000000,
        },
        {
            "corp_code": "00164779",
            "corp_name": "SK하이닉스",
            "corp_name_eng": "SK hynix",
            "stock_code": "000660",
            "induty_code": "264",
            "corp_cls": "Y",
            "capital_stock": 3657000000000,
        },
    ]
    company_query = """
    MERGE (c:Company {corp_code: $corp_code})
    SET c.corp_name = $corp_name,
        c.corp_name_eng = $corp_name_eng,
        c.stock_code = $stock_code,
        c.induty_code = $induty_code,
        c.corp_cls = $corp_cls,
        c.capital_stock = $capital_stock,
        c.updated_at = datetime()
    """
    for company in companies:
        try:
            hook.run(company_query, company)
            print(f"✓ Merged company: {company.get('corp_name')}")
        except Exception as e:
            print(f"✗ Failed to merge company {company.get('corp_code')}: {e}")
            raise

    # 4. Mark setup as complete
    mark_complete_query = "MERGE (m:Meta {name: 'kg_setup_status'}) SET m.complete = true, m.completed_at = datetime()"
    hook.run(mark_complete_query)
    print("\n✓ Marked KG setup as complete.")

    print("--- Task Finished: create_base_kg_data ---")


def extract_data_from_request(url: str = "", **kwargs):
    if url:
        source_url = url
    else:
        source_url = "https://raw.githubusercontent.com/ssilb4/test-file-storage/refs/heads/main/input.json"
    res = requests.get(source_url)
    res_json = res.json()
    return res_json


# --- Operator 3: Load Daily Data --- #


def load_daily_data(neo4j_conn_id: str, **kwargs):
    """
    Loads entities and relationships from a dictionary (passed via XComs) into Neo4j.
    """
    print("--- Starting Task: load_daily_data ---")
    ti = kwargs["ti"]
    data_to_load = ti.xcom_pull(task_ids="extract_daily_data")
    if not data_to_load:
        raise ValueError("No data received from upstream task.")

    print(f"✓ Received data for {len(data_to_load)} companies from upstream task.")
    hook = Neo4jHook(neo4j_conn_id)

    # Define all necessary Cypher queries based on documentation
    # These queries are designed to be idempotent using MERGE
    queries = {
        "Company": """
            MERGE (c:Company {stock_code: $fields.stock_code})
            ON CREATE SET c.corp_name = $fields.corp_name, c.created_at = datetime()
            ON MATCH SET c.corp_name = $fields.corp_name, c.updated_at = datetime()
        """,
        "Indicator": """
            MATCH (c:Company {stock_code: $stock_code})
            MERGE (c)-[:HAS_INDICATOR_ON]->(i:Indicator {date: date($date)})
            ON CREATE SET i.eps = $fields.eps, i.per = $fields.per, i.pbr = $fields.pbr, i.bps = $fields.bps, i.created_at = datetime()
            ON MATCH SET i.eps = $fields.eps, i.per = $fields.per, i.pbr = $fields.pbr, i.bps = $fields.bps, i.updated_at = datetime()
        """,
        "StockPrice": """
            MATCH (c:Company {stock_code: $stock_code})
            MERGE (c)-[:HAS_PRICE]->(sp:StockPrice {date: date($date)})
            ON CREATE SET sp.stck_oprc = $fields.stck_oprc, sp.stck_prpr = $fields.stck_prpr, sp.stck_hgpr = $fields.stck_hgpr, sp.stck_lwpr = $fields.stck_lwpr, sp.created_at = datetime()
            ON MATCH SET sp.stck_oprc = $fields.stck_oprc, sp.stck_prpr = $fields.stck_prpr, sp.stck_hgpr = $fields.stck_hgpr, sp.stck_lwpr = $fields.stck_lwpr, sp.updated_at = datetime()
        """,
        # Add other queries for Person, Product, Event, etc. here as the data format evolves
    }

    for company_name, company_data in data_to_load.items():
        print(f"\nProcessing: {company_name}")
        stock_code = company_data.get("test_stock_code")
        timestamp = company_data.get("timestamp")
        date_str = timestamp.split("T")[0] if timestamp else None

        if not stock_code or not date_str:
            print("  - Skipping: missing stock_code or timestamp.")
            continue

        # Process Company first to ensure it exists
        company_fields = {
            "stock_code": stock_code,
            "corp_name": company_name,
        }
        try:
            hook.run(queries["Company"], parameters={"fields": company_fields})
            print(f"  - ✓ Ensured Company exists: {company_name}")
        except Exception as e:
            print(f"  - ✗ Failed to process Company {company_name}: {e}")
            continue  # Skip to next company if we can't even process the company node

        entities = company_data.get("entities", {})
        # Process other entities
        for entity_name, entity_payload in entities.items():
            if entity_name == "Company":  # Already processed
                continue

            if entity_name in queries and (fields := entity_payload.get("fields")):
                # Prepare parameters for the query
                params = {"fields": fields, "stock_code": stock_code, "date": date_str}

                try:
                    hook.run(queries[entity_name], parameters=params)
                    print(f"  - ✓ Loaded {entity_name} data.")
                except Exception as e:
                    print(f"  - ✗ Failed to load {entity_name} data: {e}")

    print("--- Task Finished: load_daily_data ---")
