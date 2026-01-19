"""
Customs Declaration Data Models
Pydantic models for data validation and serialization
"""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional

class CustomsDeclaration(BaseModel):
    """Structured customs declaration data"""
    shipper: str = Field(..., description="Shipper name and details")
    receiver: str = Field(..., description="Receiver name and details")
    goodsDescription: str = Field(..., alias="goods_description", description="Description of goods")
    value: str = Field(..., description="Declared value with currency")
    countryOfOrigin: str = Field(..., alias="country_of_origin", description="Country where goods originated")
    hsCode: str = Field(..., alias="hs_code", description="Harmonized System code")
    weight: str = Field(..., description="Weight with unit")
    
    class Config:
        populate_by_name = True

class FieldData(BaseModel):
    """OCR extracted field data with confidence"""
    value: str
    confidence: float = Field(..., ge=0.0, le=1.0)

class OCRResponse(BaseModel):
    """Response from OCR processing"""
    document_id: str
    raw_data: Dict[str, FieldData]
    ocr_confidence: float = Field(..., ge=0.0, le=1.0)
    status: str = "analyzed"

class TransformResponse(BaseModel):
    """Response from data transformation"""
    document_id: str
    structured_data: CustomsDeclaration
    structure_confidence: float = Field(..., ge=0.0, le=1.0)
    status: str = "transformed"

class ComplianceResponse(BaseModel):
    """Response from compliance validation"""
    document_id: str
    checks: List[bool] = Field(..., min_length=5, max_length=5)
    compliance_confidence: float = Field(..., ge=0.0, le=1.0)
    issues: List[str] = []
    reasoning: Optional[str] = None
    status: str = "validated"

class UploadResponse(BaseModel):
    """Response from document upload"""
    document_id: str
    file_name: str
    file_url: Optional[str] = None
    blob_url: Optional[str] = None
    status: str = "uploaded"

class SubmissionResponse(BaseModel):
    """Response from customs submission"""
    document_id: str
    submission_id: str
    status: str = "submitted"
    timestamp: str
