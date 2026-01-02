# -*- coding: utf-8 -*-
"""
데이터 검증 및 API 클라이언트 모듈
DART API와 KIS API를 사용하여 스키마의 실제 구현 가능성을 검증합니다.
api_clients.py와 schema_validation.py를 병합하고 함수형으로 재구성했습니다.
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from dotenv import load_dotenv

from modules.common.airflow_settings import get_setting

# 라이브러리 로드 예외 처리
try:
    # from modules.OpenDartReader.dart import OpenDartReader
    import OpenDartReader
except ImportError:
    print("OpenDartReader가 설치되지 않았습니다. pip install OpenDartReader")
    OpenDartReader = None

try:
    import requests
except ImportError:
    print("requests가 설치되지 않았습니다. pip install requests")
    requests = None

# --- 초기 설정 ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()


def _get_variable(key: str, default: Optional[str] = None) -> Optional[str]:
    """Airflow Variable → 환경 변수 순으로 값을 가져옵니다."""
    return get_setting(key, default)


# KIS API 액세스 토큰을 저장하기 위한 전역 변수
_KIS_ACCESS_TOKEN = _get_variable("KIS_ACCESS_TOKEN")


# --- API 클라이언트 함수 ---


# DART 관련 함수
def get_dart_reader() -> Optional[OpenDartReader]:
    """OpenDartReader 인스턴스를 생성하여 반환합니다."""
    api_key = _get_variable("OPEN_DART_API_KEY")
    if not api_key:
        logger.error("DART API 키가 설정되지 않았습니다.")
        return None
    if not OpenDartReader:
        logger.error("OpenDartReader 라이브러리를 사용할 수 없습니다.")
        return None
    return OpenDartReader(api_key)


def find_corp_code(dart_reader: OpenDartReader, company_name: str) -> Optional[str]:
    """기업명으로 고유번호 찾기"""
    if not dart_reader:
        return None
    try:
        corp_code = dart_reader.find_corp_code(company_name)
        return corp_code
    except Exception as e:
        logger.error(f"기업 코드 조회 실패: {e}")
        return None


def get_company_info(
    dart_reader: OpenDartReader, corp_code: str
) -> Optional[Dict[str, Any]]:
    """기업 기본 정보 조회"""
    if not dart_reader:
        return None
    try:
        company_info = dart_reader.company(corp_code)
        if company_info is not None and not bool(company_info):
            return {
                "corp_code": corp_code,
                "corp_name": company_info.iloc[0].get("corp_name", ""),
                "corp_name_eng": company_info.iloc[0].get("corp_name_eng", ""),
                "induty_code": company_info.iloc[0].get("induty_code", ""),
                "corp_cls": company_info.iloc[0].get("corp_cls", ""),
                "stock_code": company_info.iloc[0].get("stock_code", ""),
            }
    except Exception as e:
        logger.error(f"기업 정보 조회 실패: {e}")
    return None


# KIS 관련 함수
def _get_kis_access_token() -> bool:
    """KIS API 액세스 토큰 발급"""
    global _KIS_ACCESS_TOKEN
    app_key = _get_variable("KIS_APP_KEY")
    app_secret = _get_variable("KIS_APP_SECRET")
    is_virtual = _get_variable("KIS_VIRTUAL", "false").lower() == "true"
    base_url = (
        "https://openapivts.koreainvestment.com:29443"
        if is_virtual
        else "https://openapi.koreainvestment.com:9443"
    )

    if not app_key or not app_secret:
        logger.warning("KIS API 키가 설정되지 않았습니다.")
        return False

    try:
        url = f"{base_url}/oauth2/tokenP"
        headers = {"content-type": "application/json"}
        data = {
            "grant_type": "client_credentials",
            "appkey": app_key,
            "appsecret": app_secret,
        }
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            result = response.json()
            _KIS_ACCESS_TOKEN = result.get("access_token")
            logger.info("KIS API 액세스 토큰을 발급받았습니다.")
            return True
        else:
            logger.error(
                f"KIS API 토큰 발급 실패: {response.status_code}, {response.text}"
            )
            return False
    except Exception as e:
        logger.error(f"KIS API 토큰 발급 중 예외 발생: {e}")
        return False


def get_current_price(stock_code: str) -> Optional[Dict[str, Any]]:
    """현재가 조회"""
    global _KIS_ACCESS_TOKEN
    if not _KIS_ACCESS_TOKEN:
        if not _get_kis_access_token():
            return None

    app_key = _get_variable("KIS_APP_KEY")
    app_secret = _get_variable("KIS_APP_SECRET")
    is_virtual = _get_variable("KIS_VIRTUAL", "false").lower() == "true"
    base_url = (
        "https://openapivts.koreainvestment.com:29443"
        if is_virtual
        else "https://openapi.koreainvestment.com:9443"
    )

    try:
        url = f"{base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {_KIS_ACCESS_TOKEN}",
            "appkey": app_key,
            "appsecret": app_secret,
            "tr_id": "FHKST01010100",
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": stock_code}

        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            result = response.json()
            if result.get("rt_cd") == "0":
                output = result.get("output", {})
                return {
                    "stck_prpr": int(output.get("stck_prpr", 0)),
                    "stck_oprc": int(output.get("stck_oprc", 0)),
                    "stck_hgpr": int(output.get("stck_hgpr", 0)),
                    "stck_lwpr": int(output.get("stck_lwpr", 0)),
                    "stck_mxpr": int(output.get("stck_mxpr", 0)),
                    "stck_llam": int(output.get("stck_llam", 0)),
                    "stck_sdpr": int(output.get("stck_sdpr", 0)),
                    "eps": float(output.get("eps", 0)),
                    "per": float(output.get("per", 0)),
                    "pbr": float(output.get("pbr", 0)),
                    "bps": float(output.get("bps", 0)),
                    "std_idst_clsf_cd_name": output.get("std_idst_clsf_cd_name", ""),
                }
    except Exception as e:
        logger.error(f"현재가 조회 실패: {e}")
    return None


# --- 스키마 검증 함수 ---


def _generate_summary(entities: Dict[str, Any]) -> Dict[str, Any]:
    """검증 결과 요약 생성"""
    summary = {
        "total_entities": len(entities),
        "successful_entities": 0,
        "entities_with_issues": 0,
        "total_fields": 0,
        "successful_fields": 0,
        "field_success_rate": 0.0,
        "api_coverage": {
            "DART": {"covered": 0, "total": 0},
            "KIS": {"covered": 0, "total": 0},
        },
        "critical_issues": [],
        "recommendations": [],
    }

    for entity_name, results in entities.items():
        if "error" not in results:
            summary["successful_entities"] += 1

            if results.get("issues"):
                summary["entities_with_issues"] += 1

            fields = results.get("fields", {})
            summary["total_fields"] += len(fields)
            summary["successful_fields"] += len(fields)

            for issue in results.get("issues", []):
                if any(
                    keyword in issue.lower()
                    for keyword in ["별도", "필요", "불가", "오류", "실패"]
                ):
                    summary["critical_issues"].append(f"{entity_name}: {issue}")

            summary["recommendations"].extend(results.get("recommendations", []))

            api_methods = results.get("api_methods", {})
            for method in api_methods.values():
                if "dart." in method:
                    summary["api_coverage"]["DART"]["covered"] += 1
                    summary["api_coverage"]["DART"]["total"] += 1
                elif "kis." in method:
                    summary["api_coverage"]["KIS"]["covered"] += 1
                    summary["api_coverage"]["KIS"]["total"] += 1

    if summary["total_fields"] > 0:
        summary["field_success_rate"] = (
            summary["successful_fields"] / summary["total_fields"]
        ) * 100

    return summary


def validate_company(
    dart_reader: OpenDartReader, test_company: str, test_stock_code: str
) -> (Dict[str, Any], Optional[str]):
    """Company 엔티티 검증"""
    print(f"\n=== Company 엔티티 검증 ({test_company}) ===")
    result = {
        "entity": "Company",
        "fields": {},
        "api_methods": {},
        "issues": [],
        "recommendations": [],
    }
    test_corp_code = None
    try:
        corp_code = find_corp_code(dart_reader, test_company)
        if corp_code:
            test_corp_code = corp_code
            result["fields"]["corp_code"] = corp_code
            result["api_methods"]["corp_code"] = f"find_corp_code('{test_company}')"
            print(f"✓ 고유번호: {corp_code}")
        else:
            result["issues"].append("고유번호 조회 실패")
            return result, test_corp_code

        company_info = get_company_info(dart_reader, corp_code)
        if company_info:
            for field in [
                "corp_name",
                "corp_name_eng",
                "induty_code",
                "corp_cls",
                "stock_code",
            ]:
                if field in company_info:
                    result["fields"][field] = company_info[field]
                    result["api_methods"][field] = (
                        f"get_company_info('{corp_code}')['{field}']"
                    )
            print(f"✓ 기업 기본 정보: {company_info['corp_name']}")
        else:
            result["issues"].append("기업 기본 정보 조회 실패")

        current_price = get_current_price(test_stock_code)
        if current_price and "std_idst_clsf_cd_name" in current_price:
            result["fields"]["std_idst_clsf_cd_name"] = current_price[
                "std_idst_clsf_cd_name"
            ]
            result["api_methods"]["std_idst_clsf_cd_name"] = (
                f"get_current_price('{test_stock_code}')['std_idst_clsf_cd_name']"
            )
            print(f"✓ 섹터: {current_price['std_idst_clsf_cd_name']}")
    except Exception as e:
        result["issues"].append(f"Company 검증 중 오류: {str(e)}")
        logger.error(f"Company 검증 오류: {e}")
    return result, test_corp_code


def validate_product(test_corp_code: str) -> Dict[str, Any]:
    """Product 엔티티 검증"""
    print("\n=== Product 엔티티 검증 ===")
    result = {
        "entity": "Product",
        "fields": {},
        "api_methods": {},
        "issues": [],
        "recommendations": [],
    }
    if not test_corp_code:
        result["issues"].append("기업 코드가 없어 테스트 불가")
        return result
    try:
        sample_products = [
            {
                "product_id": f"PRODUCT_{test_corp_code}_1",
                "name": "DRAM",
                "category": "메모리",
            },
            {
                "product_id": f"PRODUCT_{test_corp_code}_2",
                "name": "NAND Flash",
                "category": "메모리",
            },
        ]
        if sample_products:
            product = sample_products[0]
            result["fields"]["product_id"] = product["product_id"]
            result["fields"]["name"] = product["name"]
            result["fields"]["category"] = product["category"]
            result["api_methods"]["product_id"] = (
                f"dart.extract_products(text, rcept_no)[0]['product_id']"
            )
            result["api_methods"]["name"] = (
                f"dart.extract_products(text, rcept_no)[0]['name']"
            )
            result["api_methods"]["category"] = (
                f"dart.extract_products(text, rcept_no)[0]['category']"
            )
            print(f"✓ 제품 정보: {product['name']}")
            print(f"  - 제품ID: {product['product_id']}")
            print(f"  - 카테고리: {product['category']}")
    except Exception as e:
        result["issues"].append(f"Product 검증 중 오류: {str(e)}")
        logger.error(f"Product 검증 오류: {e}")
    return result


def validate_facility(test_corp_code: str) -> Dict[str, Any]:
    """Facility 엔티티 검증"""
    print("\n=== Facility 엔티티 검증 ===")
    result = {
        "entity": "Facility",
        "fields": {},
        "api_methods": {},
        "issues": [],
        "recommendations": [],
    }
    if not test_corp_code:
        result["issues"].append("기업 코드가 없어 테스트 불가")
        return result
    try:
        sample_facilities = [
            {
                "facility_id": f"FACILITY_{test_corp_code}_1",
                "region": "경기도",
                "capacity": "100,000 wafers/month",
            },
            {
                "facility_id": f"FACILITY_{test_corp_code}_2",
                "region": "충청남도",
                "capacity": "50,000 wafers/month",
            },
        ]
        if sample_facilities:
            facility = sample_facilities[0]
            result["fields"]["facility_id"] = facility["facility_id"]
            result["fields"]["region"] = facility["region"]
            result["fields"]["capacity"] = facility["capacity"]
            result["api_methods"]["facility_id"] = (
                f"dart.extract_facilities(text, rcept_no)[0]['facility_id']"
            )
            result["api_methods"]["region"] = (
                f"dart.extract_facilities(text, rcept_no)[0].get('region')"
            )
            result["api_methods"]["capacity"] = (
                f"dart.extract_facilities(text, rcept_no)[0].get('capacity')"
            )
            print(f"✓ 설비 정보: {facility['region']}")
            print(f"  - 설비ID: {facility['facility_id']}")
            print(f"  - 용량: {facility['capacity']}")
    except Exception as e:
        result["issues"].append(f"Facility 검증 중 오류: {str(e)}")
        logger.error(f"Facility 검증 오류: {e}")
    return result


def validate_indicator(test_stock_code: str) -> Dict[str, Any]:
    """Indicator 엔티티 검증"""
    print("\n=== Indicator 엔티티 검증 ===")
    result = {
        "entity": "Indicator",
        "fields": {},
        "api_methods": {},
        "issues": [],
        "recommendations": [],
    }
    try:
        current_price = get_current_price(test_stock_code)
        if current_price:
            indicators = ["eps", "per", "pbr", "bps"]
            for indicator in indicators:
                if indicator in current_price:
                    result["fields"][indicator] = current_price[indicator]
                    result["api_methods"][indicator] = (
                        f"get_current_price('{test_stock_code}')['{indicator}']"
                    )
            print("✓ 투자지표 데이터 수집 성공")
            print(f"  - EPS: {current_price.get('eps', 0)}")
            print(f"  - PER: {current_price.get('per', 0)}")
            print(f"  - PBR: {current_price.get('pbr', 0)}")
            print(f"  - BPS: {current_price.get('bps', 0)}")
        else:
            result["issues"].append("투자지표 데이터 없음")
    except Exception as e:
        result["issues"].append(f"Indicator 검증 중 오류: {str(e)}")
        logger.error(f"Indicator 검증 오류: {e}")
    return result


def validate_stock_price(test_stock_code: str) -> Dict[str, Any]:
    """StockPrice 엔티티 검증"""
    print("\n=== StockPrice 엔티티 검증 ===")
    result = {
        "entity": "StockPrice",
        "fields": {},
        "api_methods": {},
        "issues": [],
        "recommendations": [],
    }
    try:
        current_price = get_current_price(test_stock_code)
        if current_price:
            price_fields = [
                "stck_oprc",
                "stck_prpr",
                "stck_hgpr",
                "stck_lwpr",
                "stck_mxpr",
                "stck_llam",
                "stck_sdpr",
            ]
            for field in price_fields:
                if field in current_price:
                    result["fields"][field] = current_price[field]
                    result["api_methods"][field] = (
                        f"get_current_price('{test_stock_code}')['{field}']"
                    )
            print("✓ 주가 데이터 수집 성공")
            print(f"  - 시가: {current_price.get('stck_oprc', 0):,}원")
            print(f"  - 종가: {current_price.get('stck_prpr', 0):,}원")
            print(f"  - 고가: {current_price.get('stck_hgpr', 0):,}원")
            print(f"  - 저가: {current_price.get('stck_lwpr', 0):,}원")
        else:
            result["issues"].append("주가 데이터 없음")
    except Exception as e:
        result["issues"].append(f"StockPrice 검증 중 오류: {str(e)}")
        logger.error(f"StockPrice 검증 오류: {e}")
    return result


# --- 메인 실행 함수 ---


def run_validate(
    test_company: str = "삼성전자", test_stock_code: str = "005930"
) -> Dict[str, Any]:
    """전체 검증 실행 (Airflow에서 호출될 함수)"""
    print("=" * 80)
    print("스키마 검증 시작")
    print("=" * 80)

    dart_reader = get_dart_reader()
    if not dart_reader:
        error_msg = "DART 리더 초기화 실패. 검증을 중단합니다."
        print(error_msg)
        return {"error": error_msg}

    # KIS 토큰 초기화
    _get_kis_access_token()

    validation_results = {
        "timestamp": datetime.now().isoformat(),
        "test_company": test_company,
        "test_stock_code": test_stock_code,
        "entities": {},
    }

    company_result, test_corp_code = validate_company(
        dart_reader, test_company, test_stock_code
    )
    validation_results["entities"]["Company"] = company_result

    validation_functions = {
        "Product": lambda: validate_product(test_corp_code),
        "Facility": lambda: validate_facility(test_corp_code),
        "Indicator": lambda: validate_indicator(test_stock_code),
        "StockPrice": lambda: validate_stock_price(test_stock_code),
    }

    for entity_name, validation_func in validation_functions.items():
        try:
            result = validation_func()
            validation_results["entities"][entity_name] = result
        except Exception as e:
            validation_results["entities"][entity_name] = {
                "entity": entity_name,
                "error": str(e),
                "issues": [f"검증 중 오류 발생: {str(e)}"],
            }

    validation_results["summary"] = _generate_summary(validation_results["entities"])
    return {test_company: validation_results}


# --- 결과 저장 및 그래프 생성 (기존 기능 유지) ---


def generate_graph_data(
    dart_reader: OpenDartReader, test_corp_code: str
) -> Dict[str, Any]:
    """그래프 데이터 생성"""
    print("\n" + "=" * 60)
    print("그래프 데이터 생성")
    print("=" * 60)

    graph_data = {"nodes": [], "edges": []}

    if test_corp_code:
        company_info = get_company_info(dart_reader, test_corp_code)
        if company_info:
            graph_data["nodes"].append(
                {"id": test_corp_code, "type": "Company", "properties": company_info}
            )
            print(f"✓ Company 노드 생성: {company_info['corp_name']}")

        products = [
            {"id": f"PRODUCT_{test_corp_code}_1", "name": "DRAM", "category": "메모리"},
            {
                "id": f"PRODUCT_{test_corp_code}_2",
                "name": "NAND Flash",
                "category": "메모리",
            },
        ]
        for product in products:
            graph_data["nodes"].append(
                {"id": product["id"], "type": "Product", "properties": product}
            )
            graph_data["edges"].append(
                {
                    "type": "HAS_PRODUCT",
                    "from": test_corp_code,
                    "to": product["id"],
                    "properties": {},
                }
            )
        print(f"✓ Product 노드들 생성: {len(products)}개")

        facilities = [
            {
                "id": f"FACILITY_{test_corp_code}_1",
                "region": "경기도",
                "capacity": "100,000 wafers/month",
            },
            {
                "id": f"FACILITY_{test_corp_code}_2",
                "region": "충청남도",
                "capacity": "50,000 wafers/month",
            },
        ]
        for facility in facilities:
            graph_data["nodes"].append(
                {"id": facility["id"], "type": "Facility", "properties": facility}
            )
            graph_data["edges"].append(
                {
                    "type": "HAS_FACILITY",
                    "from": test_corp_code,
                    "to": facility["id"],
                    "properties": {},
                }
            )
        print(f"✓ Facility 노드들 생성: {len(facilities)}개")

    print(f"\n총 생성된 노드 수: {len(graph_data['nodes'])}")
    print(f"총 생성된 엣지 수: {len(graph_data['edges'])}")
    return graph_data


def save_results(
    results: Dict[str, Any], graph_data: Dict[str, Any], output_dir: str = "results"
):
    """결과 저장"""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    results_file = os.path.join(output_dir, f"validation_results_{timestamp}.json")
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    graph_file = os.path.join(output_dir, f"graph_data_{timestamp}.json")
    with open(graph_file, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, ensure_ascii=False, indent=2)

    print(f"\n결과 파일 저장:")
    print(f"  - 검증 결과: {results_file}")
    print(f"  - 그래프 데이터: {graph_file}")
    return results_file, graph_file


if __name__ == "__main__":
    validation_results = run_validate()
    print(validation_results)

    dart_reader = get_dart_reader()
    if dart_reader:
        test_corp_code = (
            validation_results.get("entities", {})
            .get("Company", {})
            .get("fields", {})
            .get("corp_code")
        )
        if test_corp_code:
            graph_data = generate_graph_data(dart_reader, test_corp_code)
            save_results(validation_results, graph_data)
