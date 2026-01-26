#!/usr/bin/env python3
"""
Local Testing Script for Compliance Agents

Run this script to test the compliance workflow locally with sample declarations.

Usage:
    python test_local.py [--sample SAMPLE_NAME] [--interactive]

Examples:
    python test_local.py                      # Run all sample tests
    python test_local.py --sample basic       # Run basic sample
    python test_local.py --interactive        # Interactive mode
"""

import asyncio
import argparse
import json
import os
import sys
from datetime import datetime, timedelta

# Add paths
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from dotenv import load_dotenv

# Load environment
load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))


# Sample declarations for testing
SAMPLE_DECLARATIONS = {
    "basic": {
        "name": "Basic Electronics Import",
        "data": {
            "declaration_id": "TEST-001",
            "shipper": {
                "name": "Acme Electronics Ltd",
                "address": "123 Industrial Way, Shenzhen, China",
                "country": "CN"
            },
            "consignee": {
                "name": "UK Tech Distributors",
                "address": "45 Commerce Park, Manchester, UK",
                "country": "GB"
            },
            "goods": [
                {
                    "description": "Wireless Bluetooth Headphones",
                    "hs_code": "8518300000",
                    "quantity": 5000,
                    "unit_value": 12.50,
                    "total_value": 62500.00,
                    "currency": "USD",
                    "country_of_origin": "CN"
                }
            ],
            "country_of_dispatch": "CN",
            "port_of_entry": "Felixstowe",
            "total_value": 62500.00,
            "currency": "USD",
            "transport_mode": "Sea",
            "container_number": "MSKU1234567"
        }
    },
    
    "suspicious_origin": {
        "name": "Suspicious Origin Mismatch",
        "data": {
            "declaration_id": "TEST-002",
            "shipper": {
                "name": "Global Trade FZE",
                "address": "Jebel Ali Free Zone, Dubai",
                "country": "AE"
            },
            "consignee": {
                "name": "London Import Co",
                "address": "100 Docklands, London, UK",
                "country": "GB"
            },
            "goods": [
                {
                    "description": "Steel Pipes",
                    "hs_code": "7304000000",
                    "quantity": 1000,
                    "unit_value": 45.00,
                    "total_value": 45000.00,
                    "currency": "USD",
                    "country_of_origin": "RU"  # Russian origin through UAE
                }
            ],
            "country_of_dispatch": "AE",
            "port_of_entry": "Southampton",
            "total_value": 45000.00,
            "currency": "USD",
            "transport_mode": "Sea"
        }
    },
    
    "potential_sanctions": {
        "name": "Potential Sanctions Concern",
        "data": {
            "declaration_id": "TEST-003",
            "shipper": {
                "name": "Petrov Industrial Supplies",
                "address": "45 Nevsky Prospekt, Moscow",
                "country": "RU"
            },
            "consignee": {
                "name": "Northern Engineering Ltd",
                "address": "Edinburgh, Scotland, UK",
                "country": "GB"
            },
            "goods": [
                {
                    "description": "Industrial Ball Bearings",
                    "hs_code": "8482100000",
                    "quantity": 10000,
                    "unit_value": 5.00,
                    "total_value": 50000.00,
                    "currency": "USD",
                    "country_of_origin": "RU"
                }
            ],
            "country_of_dispatch": "RU",
            "port_of_entry": "Hull",
            "total_value": 50000.00,
            "currency": "USD",
            "transport_mode": "Sea"
        }
    },
    
    "dual_use": {
        "name": "Potential Dual-Use Goods",
        "data": {
            "declaration_id": "TEST-004",
            "shipper": {
                "name": "Precision Tech GmbH",
                "address": "Munich, Germany",
                "country": "DE"
            },
            "consignee": {
                "name": "Defense Research Ltd",
                "address": "Bristol, UK",
                "country": "GB"
            },
            "goods": [
                {
                    "description": "High-precision CNC milling machine, 5-axis",
                    "hs_code": "8459610000",
                    "quantity": 1,
                    "unit_value": 250000.00,
                    "total_value": 250000.00,
                    "currency": "EUR",
                    "country_of_origin": "DE"
                },
                {
                    "description": "Thermal imaging camera modules",
                    "hs_code": "9013801000",
                    "quantity": 50,
                    "unit_value": 2000.00,
                    "total_value": 100000.00,
                    "currency": "EUR",
                    "country_of_origin": "DE"
                }
            ],
            "country_of_dispatch": "DE",
            "port_of_entry": "Southampton",
            "total_value": 350000.00,
            "currency": "EUR",
            "transport_mode": "Road"
        }
    },
    
    "undervaluation": {
        "name": "Suspected Undervaluation",
        "data": {
            "declaration_id": "TEST-005",
            "shipper": {
                "name": "Budget Electronics Co",
                "address": "Guangzhou, China",
                "country": "CN"
            },
            "consignee": {
                "name": "Discount Gadgets UK",
                "address": "Birmingham, UK",
                "country": "GB"
            },
            "goods": [
                {
                    "description": "Apple iPhone 15 Pro Max smartphones",
                    "hs_code": "8517130000",
                    "quantity": 1000,
                    "unit_value": 50.00,  # Suspiciously low for iPhone 15 Pro Max
                    "total_value": 50000.00,
                    "currency": "USD",
                    "country_of_origin": "CN"
                }
            ],
            "country_of_dispatch": "CN",
            "port_of_entry": "Heathrow",
            "total_value": 50000.00,
            "currency": "USD",
            "transport_mode": "Air"
        }
    },
    
    "inconsistent": {
        "name": "Inconsistent Declaration",
        "data": {
            "declaration_id": "TEST-006",
            "shipper": {
                "name": "FastShip Logistics",
                "address": "Hong Kong",
                "country": "HK"
            },
            "consignee": {
                "name": "UK Wholesale Ltd",
                "address": "Leeds, UK",
                "country": "GB"
            },
            "goods": [
                {
                    "description": "Fresh frozen seafood - salmon fillets",  # Fresh AND frozen?
                    "hs_code": "0302140000",  # Fresh fish code
                    "quantity": 500,
                    "unit_value": 25.00,
                    "total_value": 12000.00,  # Doesn't match 500 x 25
                    "currency": "GBP",
                    "country_of_origin": "NO"  # Norway origin from Hong Kong?
                }
            ],
            "country_of_dispatch": "HK",
            "port_of_entry": "Felixstowe",
            "total_value": 15000.00,  # Different from goods total
            "currency": "USD",  # Different currency than goods
            "transport_mode": "Air"  # Air freight for frozen seafood from HK?
        }
    }
}


async def run_test(sample_name: str, declaration_data: dict):
    """Run a single test with the compliance workflow."""
    from workflow import run_compliance_check
    from tools import initialize_services
    
    print(f"\n{'=' * 70}")
    print(f"Testing: {sample_name}")
    print(f"{'=' * 70}")
    print(f"\nDeclaration ID: {declaration_data.get('declaration_id', 'N/A')}")
    
    # Show key details
    if 'shipper' in declaration_data:
        print(f"Shipper: {declaration_data['shipper'].get('name', 'Unknown')} ({declaration_data['shipper'].get('country', '?')})")
    if 'consignee' in declaration_data:
        print(f"Consignee: {declaration_data['consignee'].get('name', 'Unknown')}")
    if 'goods' in declaration_data:
        print(f"Goods: {len(declaration_data['goods'])} item(s)")
        for i, good in enumerate(declaration_data['goods'][:3], 1):
            print(f"  {i}. {good.get('description', 'Unknown')[:50]} (HS: {good.get('hs_code', '?')})")
    print(f"Total Value: {declaration_data.get('total_value', '?')} {declaration_data.get('currency', '?')}")
    
    print("\nRunning compliance analysis...")
    start_time = datetime.now()
    
    try:
        # Run the compliance check
        report = await run_compliance_check(declaration_data)
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        # Display results
        print(f"\n{'─' * 50}")
        print(f"COMPLIANCE REPORT")
        print(f"{'─' * 50}")
        print(f"Overall Risk: {report.overall_risk.upper()}")
        print(f"Total Findings: {report.total_findings}")
        print(f"Manual Review Required: {'YES' if report.requires_manual_review else 'No'}")
        print(f"Processing Time: {elapsed:.2f}s")
        
        # Show findings by severity
        if report.findings:
            print(f"\nFindings by Agent:")
            by_agent = {}
            for finding in report.findings:
                agent = finding.agent_name
                if agent not in by_agent:
                    by_agent[agent] = []
                by_agent[agent].append(finding)
            
            for agent, findings in by_agent.items():
                print(f"\n  [{agent}]")
                for f in findings[:5]:  # Show first 5 per agent
                    severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(f.severity, "⚪")
                    print(f"    {severity_icon} {f.severity.upper()}: {f.summary[:60]}...")
                if len(findings) > 5:
                    print(f"    ... and {len(findings) - 5} more")
        
        # Show recommendations
        if report.recommendations:
            print(f"\nRecommendations:")
            for i, rec in enumerate(report.recommendations[:5], 1):
                print(f"  {i}. {rec[:70]}...")
        
        return report
        
    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"\n❌ ERROR after {elapsed:.2f}s: {e}")
        import traceback
        traceback.print_exc()
        return None


async def run_all_tests():
    """Run all sample tests."""
    print("=" * 70)
    print("COMPLIANCE WORKFLOW TEST SUITE")
    print("=" * 70)
    print(f"Starting at: {datetime.now().isoformat()}")
    print(f"Number of samples: {len(SAMPLE_DECLARATIONS)}")
    
    # Initialize services once
    from tools import initialize_services
    
    try:
        from app.services.hs_code_reference import HSCodeReferenceService
        from app.services.sanctions_reference import SanctionsReferenceService
        
        hs_service = HSCodeReferenceService()
        sanctions_service = SanctionsReferenceService()
        initialize_services(hs_service, sanctions_service)
        print("✓ Reference services initialized")
    except Exception as e:
        print(f"⚠ Warning: Could not initialize reference services: {e}")
        print("  Tests will run with limited functionality")
    
    results = {}
    for sample_key, sample in SAMPLE_DECLARATIONS.items():
        result = await run_test(sample["name"], sample["data"])
        results[sample_key] = result
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for r in results.values() if r is not None)
    print(f"Tests Run: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(results) - passed}")
    
    print("\nRisk Distribution:")
    risk_counts = {}
    for key, result in results.items():
        if result:
            risk = result.overall_risk
            risk_counts[risk] = risk_counts.get(risk, 0) + 1
    
    for risk, count in sorted(risk_counts.items()):
        icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(risk, "⚪")
        print(f"  {icon} {risk.upper()}: {count}")


async def interactive_mode():
    """Run in interactive mode."""
    from tools import initialize_services
    from workflow import run_compliance_check
    
    print("=" * 70)
    print("COMPLIANCE WORKFLOW - INTERACTIVE MODE")
    print("=" * 70)
    print("\nCommands:")
    print("  sample <name>  - Run a sample (basic, suspicious_origin, potential_sanctions, dual_use, undervaluation, inconsistent)")
    print("  json           - Enter custom JSON declaration")
    print("  list           - List available samples")
    print("  quit           - Exit")
    
    # Initialize services
    try:
        from app.services.hs_code_reference import HSCodeReferenceService
        from app.services.sanctions_reference import SanctionsReferenceService
        
        hs_service = HSCodeReferenceService()
        sanctions_service = SanctionsReferenceService()
        initialize_services(hs_service, sanctions_service)
        print("\n✓ Reference services initialized")
    except Exception as e:
        print(f"\n⚠ Warning: {e}")
    
    while True:
        try:
            cmd = input("\n> ").strip().lower()
            
            if not cmd:
                continue
            
            if cmd in ['quit', 'exit', 'q']:
                break
            
            if cmd == 'list':
                print("\nAvailable samples:")
                for key, sample in SAMPLE_DECLARATIONS.items():
                    print(f"  {key}: {sample['name']}")
                continue
            
            if cmd.startswith('sample '):
                sample_key = cmd.split(' ', 1)[1]
                if sample_key in SAMPLE_DECLARATIONS:
                    sample = SAMPLE_DECLARATIONS[sample_key]
                    await run_test(sample["name"], sample["data"])
                else:
                    print(f"Unknown sample: {sample_key}")
                    print(f"Available: {', '.join(SAMPLE_DECLARATIONS.keys())}")
                continue
            
            if cmd == 'json':
                print("Enter JSON declaration (paste and press Enter twice):")
                lines = []
                while True:
                    line = input()
                    if not line and lines and not lines[-1]:
                        break
                    lines.append(line)
                
                try:
                    declaration_data = json.loads('\n'.join(lines))
                    await run_test("Custom Declaration", declaration_data)
                except json.JSONDecodeError as e:
                    print(f"Invalid JSON: {e}")
                continue
            
            print(f"Unknown command: {cmd}")
            print("Try: sample <name>, json, list, or quit")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")
    
    print("\nGoodbye!")


def main():
    parser = argparse.ArgumentParser(description="Test the compliance workflow locally")
    parser.add_argument('--sample', type=str, help="Run a specific sample test")
    parser.add_argument('--interactive', '-i', action='store_true', help="Run in interactive mode")
    parser.add_argument('--list', '-l', action='store_true', help="List available samples")
    
    args = parser.parse_args()
    
    if args.list:
        print("Available samples:")
        for key, sample in SAMPLE_DECLARATIONS.items():
            print(f"  {key}: {sample['name']}")
        return
    
    if args.interactive:
        asyncio.run(interactive_mode())
    elif args.sample:
        if args.sample in SAMPLE_DECLARATIONS:
            sample = SAMPLE_DECLARATIONS[args.sample]
            asyncio.run(run_test(sample["name"], sample["data"]))
        else:
            print(f"Unknown sample: {args.sample}")
            print(f"Available: {', '.join(SAMPLE_DECLARATIONS.keys())}")
    else:
        asyncio.run(run_all_tests())


if __name__ == "__main__":
    main()
