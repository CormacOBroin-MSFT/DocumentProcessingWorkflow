"""
Azure OpenAI LLM Service
Handles LLM calls for data transformation and compliance checking via Azure AI Foundry
"""
import json
import logging
from typing import Dict, List, Optional
from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from app.config import config
from app.agent_prompts import (
    DATA_TRANSFORMATION_SYSTEM_PROMPT,
    COMPLIANCE_VALIDATION_SYSTEM_PROMPT,
    DATA_TRANSFORMATION_USER_PROMPT_TEMPLATE,
    COMPLIANCE_VALIDATION_USER_PROMPT_TEMPLATE
)

logger = logging.getLogger('autonomousflow.llm')

class LLMService:
    """Service for LLM-based data processing using Azure OpenAI"""
    
    def __init__(self):
        if not config.AZURE_OPENAI_ENDPOINT:
            raise ValueError("Azure OpenAI endpoint not configured")
        if not config.AZURE_OPENAI_DEPLOYMENT:
            raise ValueError("Azure OpenAI deployment name not configured")
        
        # Use API key if provided, otherwise use DefaultAzureCredential (Azure CLI login)
        if config.AZURE_OPENAI_KEY:
            self.client = AzureOpenAI(
                api_key=config.AZURE_OPENAI_KEY,
                api_version="2024-02-01",
                azure_endpoint=config.AZURE_OPENAI_ENDPOINT
            )
        else:
            # Get token from Azure CLI credentials
            credential = DefaultAzureCredential()
            token = credential.get_token("https://cognitiveservices.azure.com/.default")
            
            self.client = AzureOpenAI(
                api_key=token.token,  # Use the token as API key
                api_version="2024-02-01",
                azure_endpoint=config.AZURE_OPENAI_ENDPOINT
            )
            # Store credential for token refresh if needed
            self._credential = credential
        
        self.model = config.AZURE_OPENAI_DEPLOYMENT
    
    def transform_to_structured_data(self, raw_data: Dict) -> Dict:
        """
        Transform raw OCR data into structured customs declaration using agent framework
        
        Args:
            raw_data: Dictionary of key-value pairs from OCR
            
        Returns:
            Dict with structured_data (including per-field confidence) and structure_confidence
        """
        # Enhanced user prompt to request per-field confidence
        user_prompt = f"""
Transform the following raw OCR data into structured customs declaration format.

Raw OCR Data:
{json.dumps(raw_data, indent=2)}

Return a JSON object with:
1. "structured_data": object where each field has "value" and "confidence" properties
2. "structure_confidence": overall confidence score (0-1)

Required fields in structured_data:
- shipper: {{"value": "company/person name", "confidence": 0.0-1.0}}
- receiver: {{"value": "company/person name", "confidence": 0.0-1.0}}
- goodsDescription: {{"value": "description of goods", "confidence": 0.0-1.0}}
- value: {{"value": "monetary value with currency", "confidence": 0.0-1.0}}
- countryOfOrigin: {{"value": "origin country", "confidence": 0.0-1.0}}
- hsCode: {{"value": "harmonized system code", "confidence": 0.0-1.0}}
- weight: {{"value": "weight with unit", "confidence": 0.0-1.0}}

Confidence Guidelines:
- 0.9-1.0: Explicitly stated and clear in document
- 0.7-0.9: Clearly derivable from context  
- 0.5-0.7: Reasonable inference from available data
- 0.3-0.5: Educated guess based on partial information
- 0.0-0.3: Very uncertain or missing data

Return ONLY valid JSON.
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": DATA_TRANSFORMATION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Ensure proper structure with per-field confidence
            if "structured_data" not in result:
                raise ValueError("Response missing structured_data")
            if "structure_confidence" not in result:
                # Calculate structure_confidence if not provided
                field_confidences = []
                for field_data in result["structured_data"].values():
                    if isinstance(field_data, dict) and "confidence" in field_data:
                        field_confidences.append(field_data["confidence"])
                result["structure_confidence"] = sum(field_confidences) / len(field_confidences) if field_confidences else 0.5
            
            # Validate each field has value and confidence
            for field_name, field_data in result["structured_data"].items():
                if not isinstance(field_data, dict):
                    # Convert legacy string format
                    result["structured_data"][field_name] = {
                        "value": str(field_data),
                        "confidence": 0.5
                    }
                elif "value" not in field_data or "confidence" not in field_data:
                    # Ensure both value and confidence exist
                    if "value" not in field_data:
                        field_data["value"] = str(field_data.get(list(field_data.keys())[0], ""))
                    if "confidence" not in field_data:
                        field_data["confidence"] = 0.5
            
            structure_confidence = result["structure_confidence"]
            
            return result
        
        except Exception as e:
            logger.error(f"Error in LLM transformation: {e}")
            raise
    
    def perform_compliance_check(self, structured_data: Dict) -> Dict:
        """
        Validate customs declaration against compliance requirements using agent framework
        
        Args:
            structured_data: Structured customs declaration
            
        Returns:
            Dict with checks, confidence, reasoning, and risk_level
        """
        user_prompt = COMPLIANCE_VALIDATION_USER_PROMPT_TEMPLATE.format(
            structured_data=json.dumps(structured_data, indent=2)
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": COMPLIANCE_VALIDATION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            checks = result.get('checks', [True, True, True, True, True])
            check_names = [
                'HS Code Validation',
                'Country Restrictions', 
                'Value Declaration',
                'Shipper Verification',
                'Document Completeness'
            ]
            default_descriptions = [
                'HS code format validated' if checks[0] else 'HS code format invalid',
                'No country restrictions found' if checks[1] else 'Country restrictions apply',
                'Value declaration acceptable' if checks[2] else 'Value declaration issue',
                'Shipper verified' if checks[3] else 'Shipper verification failed',
                'Document complete' if checks[4] else 'Document incomplete'
            ]
            
            return {
                'checks': checks,
                'compliance_confidence': result.get('confidence', 0.88),
                'reasoning': result.get('reasoning', 'Compliance check completed'),
                'risk_level': result.get('risk_level', 'MEDIUM'),
                'issue_descriptions': result.get('issue_descriptions', default_descriptions),
                'issues': [
                    check_name for check_name, passed in zip(check_names, checks) if not passed
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
