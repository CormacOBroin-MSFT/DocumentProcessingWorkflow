/**
 * Shared type definitions for customs declaration processing
 * Single source of truth for frontend types
 */

// Core customs declaration structure
export type CustomsDeclaration = {
    shipper: string
    receiver: string
    goodsDescription: string
    value: string
    countryOfOrigin: string
    hsCode: string
    weight: string
}

// Field-level confidence data from OCR/AI extraction
export type FieldConfidence = {
    value: string
    confidence: number
}

// Structured data with per-field confidence scores
export type StructuredDataWithConfidence = {
    shipper: FieldConfidence
    receiver: FieldConfidence
    goodsDescription: FieldConfidence
    value: FieldConfidence
    countryOfOrigin: FieldConfidence
    hsCode: FieldConfidence
    weight: FieldConfidence
}

// Aggregate confidence scores for a document
export type ConfidenceScores = {
    ocr: number
    structure: number
    compliance: number
}

// Document data as it progresses through workflow
export type DocumentData = {
    fileName: string
    fileUrl: string
    fileType?: string
    blobUrl?: string
    rawData?: Record<string, FieldConfidence>
    structuredData?: CustomsDeclaration
    confidenceScores?: ConfidenceScores
}

// Compliance issue detected during validation
export type ComplianceIssue = {
    field: keyof CustomsDeclaration
    type: 'missing' | 'invalid' | 'ambiguous' | 'low_confidence'
    title: string
    description: string
    hint: string
    checkIndex?: number
}

// Workflow stage status (the status value)
export type StageStatusValue = 'inactive' | 'active' | 'processing' | 'completed' | 'pending' | 'complete' | 'in-progress'

// Stage status object for tracking workflow stages
export type StageStatus = {
    name: string
    status: StageStatusValue
}

// Workflow mode
export type WorkflowMode = 'manual' | 'automated'

// Automated workflow step
export type AutomatedStep = 'idle' | 'upload' | 'processing' | 'approval' | 'complete'

// Processing step status
export type ProcessingStepStatus = 'pending' | 'in-progress' | 'complete' | 'error' | 'warning'

export type ProcessingStep = {
    id: string
    label: string
    status: ProcessingStepStatus
    warningMessage?: string
}

// Helper to extract values from structured data with confidence
export function extractValuesFromStructuredData(
    data: StructuredDataWithConfidence | CustomsDeclaration
): CustomsDeclaration {
    // If it's already a plain CustomsDeclaration, return as-is
    if (typeof data.shipper === 'string') {
        return data as CustomsDeclaration
    }
    // Extract values from {value, confidence} structure
    const withConfidence = data as StructuredDataWithConfidence
    return {
        shipper: withConfidence.shipper?.value ?? '',
        receiver: withConfidence.receiver?.value ?? '',
        goodsDescription: withConfidence.goodsDescription?.value ?? '',
        value: withConfidence.value?.value ?? '',
        countryOfOrigin: withConfidence.countryOfOrigin?.value ?? '',
        hsCode: withConfidence.hsCode?.value ?? '',
        weight: withConfidence.weight?.value ?? '',
    }
}

// Calculate overall confidence from individual scores
export function calculateOverallConfidence(scores: ConfidenceScores): number {
    const weights = {
        ocr: 0.3,
        structure: 0.3,
        compliance: 0.4,
    }

    return (
        scores.ocr * weights.ocr +
        scores.structure * weights.structure +
        scores.compliance * weights.compliance
    )
}
