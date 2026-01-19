"""
OpenAI LLM Service
Handles LLM calls for data transformation and compliance checking
"""
import json
from typing import Dict, List, Optional
from openai import OpenAI
from app.config import config

class LLMService:
    """Service for LLM-based data processing"""
    
    def __init__(self):
        if not config.OPENAI_API_KEY:
            raise ValueError("OpenAI API key not configured")
        
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)
        self.model = config.OPENAI_MODEL
    
    def transform_to_structured_data(self, raw_data: Dict) -> Dict:
        """
        Transform raw OCR data into structured customs declaration
        
        Args:
            raw_data: Dictionary of key-value pairs from OCR
            
        Returns:
            Dict with structured_data and confidence score
        """
        prompt = f"""You are a customs document processing AI. Transform the following raw OCR data into a structured customs declaration format.

Raw data:
{json.dumps(raw_data, indent=2)}

Return a JSON object with these exact fields:
- shipper: string (company or person sending goods)
- receiver: string (company or person receiving goods)
- goodsDescription: string (what is being shipped)
- value: string (monetary value with currency)
- countryOfOrigin: string (where goods are from)
- hsCode: string (harmonized system code if available, otherwise best guess)
- weight: string (weight with unit)

Extract the most relevant information from the raw data for each field. If a field is not clearly present, make a reasonable inference based on available data.

Return ONLY valid JSON, no additional text."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a customs document processing AI that returns only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3
            )
            
            result = json.loads(response.choices[0].message.content)
            
            total_confidence = sum(
                item['confidence'] for item in raw_data.values() 
                if isinstance(item, dict) and 'confidence' in item
            )
            field_count = sum(
                1 for item in raw_data.values() 
                if isinstance(item, dict) and 'confidence' in item
            )
            
            structure_confidence = total_confidence / field_count if field_count > 0 else 0.85
            
            return {
                'structured_data': result,
                'structure_confidence': structure_confidence
            }
        
        except Exception as e:
            print(f"Error in LLM transformation: {e}")
            raise
    
    def perform_compliance_check(self, structured_data: Dict) -> Dict:
        """
        Validate customs declaration against compliance requirements
        
        Args:
            structured_data: Structured customs declaration
            
        Returns:
            Dict with checks, confidence, and reasoning
        """
        prompt = f"""You are a customs compliance validation AI. Analyze the following customs declaration and validate it against standard compliance requirements.

Customs Declaration:
{json.dumps(structured_data, indent=2)}

Validate the following 5 checks and provide a confidence score (0-1) for overall compliance:
1. HS Code Validation: Is the HS code valid and appropriate for the goods description?
2. Country Restrictions: Are there any known restrictions between origin and destination?
3. Value Declaration: Is the value reasonable for the goods and weight described?
4. Shipper Verification: Does the shipper name appear legitimate and complete?
5. Document Completeness: Are all required fields present and properly formatted?

Return a JSON object with:
- checks: array of 5 booleans (true = pass, false = fail)
- confidence: number between 0 and 1 representing overall compliance confidence
- reasoning: brief explanation for any failed checks (or "All checks passed" if all pass)

Return ONLY valid JSON, no additional text."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a customs compliance AI that returns only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3
            )
            
            result = json.loads(response.choices[0].message.content)
            
            return {
                'checks': result.get('checks', [True, True, True, True, True]),
                'compliance_confidence': result.get('confidence', 0.88),
                'reasoning': result.get('reasoning', 'Compliance check completed'),
                'issues': [
                    check_name for i, (check_name, passed) in enumerate([
                        ('HS Code Validation', result.get('checks', [True]*5)[0]),
                        ('Country Restrictions', result.get('checks', [True]*5)[1]),
                        ('Value Declaration', result.get('checks', [True]*5)[2]),
                        ('Shipper Verification', result.get('checks', [True]*5)[3]),
                        ('Document Completeness', result.get('checks', [True]*5)[4])
                    ]) if not passed
                ]
            }
        
        except Exception as e:
            print(f"Error in LLM compliance check: {e}")
            raise

def get_llm_service() -> Optional[LLMService]:
    """Factory function to get LLM service instance"""
    try:
        return LLMService()
    except Exception as e:
        print(f"Could not initialize LLM Service: {e}")
        return None
