/**
 * Application-wide constants
 * Eliminates magic numbers and centralizes configuration
 */

// Confidence thresholds
export const CONFIDENCE_THRESHOLD = {
    LOW: 0.5,
    MEDIUM: 0.7,
    HIGH: 0.85,
} as const

// Timing delays (ms)
export const DELAYS = {
    STEP_TRANSITION: 800,
    UPLOAD_TICK: 100,
    SCAN_ANIMATION: 1500,
    SUBMIT_ANIMATION: 2000,
    COSMOSDB_STORE: 1500,
} as const

// Compliance check configuration
export const COMPLIANCE = {
    CHECK_COUNT: 5,
    CHECK_NAMES: [
        'HS Code Validation',
        'Country Restrictions',
        'Value Declaration',
        'Shipper Verification',
        'Document Completeness',
    ] as const,
} as const

// API configuration
export const API_CONFIG = {
    BASE_URL: import.meta.env.VITE_API_URL || 'http://localhost:5000',
    MAX_FILE_SIZE: 16 * 1024 * 1024, // 16MB
    ACCEPTED_FILE_TYPES: ['image/png', 'image/jpeg', 'image/jpg', 'application/pdf'],
} as const

// Field metadata for display
export const FIELD_LABELS: Record<string, string> = {
    shipper: 'Exporter / Shipper',
    receiver: 'Importer / Receiver',
    goodsDescription: 'Goods Description',
    value: 'Declared Value',
    countryOfOrigin: 'Country of Origin',
    hsCode: 'HS Code',
    weight: 'Weight',
} as const

export const FIELD_HINTS: Record<string, string> = {
    shipper: 'Full legal name and address of the exporting party',
    receiver: 'Full legal name and address of the importing party',
    goodsDescription: 'Detailed description of goods being shipped',
    value: 'Transaction value in currency (e.g., 1500.00 EUR)',
    countryOfOrigin: 'Country where goods were manufactured or produced',
    hsCode: 'Harmonized System code for tariff classification',
    weight: 'Gross weight with unit (e.g., 25 KG)',
} as const

// Map compliance checks to fields
export const COMPLIANCE_TO_FIELD: Record<number, string> = {
    0: 'hsCode',
    1: 'countryOfOrigin',
    2: 'value',
    3: 'shipper',
    // 4 is document completeness - affects multiple fields
} as const

// Workflow stages configuration
export const WORKFLOW_STAGES = [
    { name: 'Upload Document', label: 'Document Intake' },
    { name: 'Azure Storage', label: 'Data Collection' },
    { name: 'Content Understanding', label: 'OCR + Transformation' },
    { name: 'Customs Fields', label: 'Declaration Data' },
    { name: 'Compliance Check', label: 'Automated Validation' },
    { name: 'Approval Workflow', label: 'Human Review' },
    { name: 'Customs Submission', label: 'Authority Filing' },
    { name: 'CosmosDB', label: 'Analytics Store' },
] as const

// Return to automation reasons
export const RETURN_REASONS = [
    { value: 'bad_scan', label: 'Poor scan quality - needs re-upload' },
    { value: 'wrong_doc', label: 'Wrong document type' },
    { value: 'missing_pages', label: 'Missing pages' },
    { value: 'ocr_errors', label: 'Too many extraction errors' },
    { value: 'other', label: 'Other reason' },
] as const
