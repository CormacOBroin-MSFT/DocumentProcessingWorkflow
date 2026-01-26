/**
 * API client for document processing services
 * Uses React Query for caching, retries, and state management
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { toast } from 'sonner'
import { API_CONFIG } from '@/constants'
import type {
    CustomsDeclaration,
    StructuredDataWithConfidence,
    ConfidenceScores,
} from '@/types/customs'

// ----- Zod Schemas for API Response Validation -----

const FieldConfidenceSchema = z.object({
    value: z.string(),
    confidence: z.number().min(0).max(1),
}).passthrough()

const StructuredDataSchema = z.object({
    shipper: FieldConfidenceSchema.optional(),
    receiver: FieldConfidenceSchema.optional(),
    goodsDescription: FieldConfidenceSchema.optional(),
    value: FieldConfidenceSchema.optional(),
    countryOfOrigin: FieldConfidenceSchema.optional(),
    hsCode: FieldConfidenceSchema.optional(),
    weight: FieldConfidenceSchema.optional(),
}).passthrough()

const StatusResponseSchema = z.object({
    azureConfigured: z.boolean(),
    openaiConfigured: z.boolean(),
    services: z.object({
        storage: z.boolean(),
        documentIntelligence: z.boolean(),
        openai: z.boolean(),
    }).optional(),
})

const UploadResponseSchema = z.object({
    blob_url: z.string().optional(),
    url: z.string().optional(),
    document_id: z.string().optional(),
})

const OCRResponseSchema = z.object({
    document_id: z.string().nullable().optional(),
    structured_data: z.record(z.string(), z.any()).nullable().optional(),
    raw_data: z.record(z.string(), z.any()).nullable().optional(),
    ocr_confidence: z.number().optional(),
    fields_extracted: z.number().optional(),
    total_fields: z.number().optional(),
    extraction_warning: z.string().optional(),
    status: z.string().optional(),
}).passthrough()

const TransformResponseSchema = z.object({
    structured_data: z.record(z.string(), z.any()),
    structure_confidence: z.number().min(0).max(1),
})

const ComplianceResponseSchema = z.object({
    checks: z.array(z.boolean()),
    compliance_confidence: z.number().min(0).max(1),
    issue_descriptions: z.array(z.string()).optional(),
    reasoning: z.string().optional(),
    risk_level: z.string().optional(),
})

// ----- API Functions -----

async function fetchWithValidation<T>(
    url: string,
    schema: z.ZodSchema<T>,
    options?: RequestInit
): Promise<T> {
    const response = await fetch(url, options)

    if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`API Error (${response.status}): ${errorText}`)
    }

    const data = await response.json()
    return schema.parse(data)
}

// Check backend status
export async function checkAzureStatus(): Promise<{ configured: boolean; openai: boolean }> {
    try {
        const data = await fetchWithValidation(
            `${API_CONFIG.BASE_URL}/api/status`,
            StatusResponseSchema
        )
        return {
            configured: data.azureConfigured,
            openai: data.openaiConfigured,
        }
    } catch (error) {
        console.warn('Could not check backend status:', error)
        return { configured: false, openai: false }
    }
}

// Upload file to Azure Blob Storage
export async function uploadToAzureBlob(file: File): Promise<string> {
    const formData = new FormData()
    formData.append('file', file)

    const response = await fetch(`${API_CONFIG.BASE_URL}/api/upload`, {
        method: 'POST',
        body: formData,
    })

    if (!response.ok) {
        throw new Error(`Upload failed: ${response.statusText}`)
    }

    const data = UploadResponseSchema.parse(await response.json())
    const blobUrl = data.blob_url || data.url

    if (!blobUrl) {
        throw new Error('No blob URL returned from upload')
    }

    return blobUrl
}

// Analyze document with AI (OCR + extraction)
export async function analyzeDocument(blobUrl: string): Promise<{
    rawData: Record<string, { value: string; confidence: number }>
    structuredData: StructuredDataWithConfidence | null
    ocrConfidence: number
    fieldsExtracted: number
    totalFields: number
    extractionWarning?: string
}> {
    const response = await fetch(`${API_CONFIG.BASE_URL}/api/ocr/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ blob_url: blobUrl }),
    })

    if (!response.ok) {
        const errorText = await response.text()
        console.error('OCR API error response:', errorText)
        throw new Error(`OCR analysis failed: ${response.statusText}`)
    }

    const jsonData = await response.json()
    console.log('OCR API raw response:', jsonData)

    let result
    try {
        result = OCRResponseSchema.parse(jsonData)
    } catch (parseError) {
        console.error('Zod parse error:', parseError)
        // Fallback: use the raw data directly if Zod parsing fails
        result = jsonData
    }
    console.log('OCR API parsed result:', result)

    // Check if structured data was extracted
    const hasStructuredData = result.structured_data &&
        Object.values(result.structured_data).some((field: any) => field?.value)

    return {
        rawData: (result.raw_data || {}) as Record<string, { value: string; confidence: number }>,
        structuredData: hasStructuredData ? result.structured_data as StructuredDataWithConfidence : null,
        ocrConfidence: result.ocr_confidence || 0,
        fieldsExtracted: result.fields_extracted || 0,
        totalFields: result.total_fields || 7,
        extractionWarning: result.extraction_warning,
    }
}

// Transform raw data to structured format
export async function transformToStructuredData(
    rawData: Record<string, { value: string; confidence: number }>
): Promise<{ structuredData: CustomsDeclaration; structureConfidence: number }> {
    const response = await fetch(`${API_CONFIG.BASE_URL}/api/transform/structure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ raw_data: rawData }),
    })

    if (!response.ok) {
        throw new Error(`Transform failed: ${response.statusText}`)
    }

    const result = TransformResponseSchema.parse(await response.json())

    // Extract plain values from per-field confidence format
    const sd = result.structured_data as Record<string, unknown>
    const structuredData: CustomsDeclaration = {
        shipper: getFieldValue(sd, 'shipper'),
        receiver: getFieldValue(sd, 'receiver'),
        goodsDescription: getFieldValue(sd, 'goodsDescription'),
        value: getFieldValue(sd, 'value'),
        countryOfOrigin: getFieldValue(sd, 'countryOfOrigin'),
        hsCode: getFieldValue(sd, 'hsCode'),
        weight: getFieldValue(sd, 'weight'),
    }

    return {
        structuredData,
        structureConfidence: result.structure_confidence,
    }
}

// Helper to extract field value from various formats
function getFieldValue(data: Record<string, unknown>, key: string): string {
    const field = data[key]
    if (typeof field === 'string') return field
    if (field && typeof field === 'object' && 'value' in field) {
        return String((field as { value: unknown }).value || '')
    }
    return ''
}

// Perform compliance validation
export async function performComplianceCheck(data: CustomsDeclaration): Promise<{
    checks: boolean[]
    complianceConfidence: number
    issueDescriptions: string[]
}> {
    const response = await fetch(`${API_CONFIG.BASE_URL}/api/compliance/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ structured_data: data }),
    })

    if (!response.ok) {
        throw new Error(`Compliance check failed: ${response.statusText}`)
    }

    const result = ComplianceResponseSchema.parse(await response.json())

    return {
        checks: result.checks,
        complianceConfidence: result.compliance_confidence,
        issueDescriptions: result.issue_descriptions || [],
    }
}

// Cosmos DB Storage Response Schema
const CosmosStoreResponseSchema = z.object({
    documentId: z.string().optional(),
    id: z.string().optional(),
    status: z.string(),
    createdAt: z.string().optional(),
    message: z.string().optional(),
})

// Store declaration in Cosmos DB
export async function storeInCosmosDB(data: {
    documentId?: string
    fileName?: string
    blobUrl?: string
    structuredData: CustomsDeclaration
    confidenceScores?: { ocr: number; structure: number; compliance: number }
    complianceChecks?: boolean[]
    complianceDescriptions?: string[]
    approvalStatus?: string
    reviewerNotes?: string
    submissionId?: string
}): Promise<{
    documentId: string
    status: string
    createdAt?: string
    message?: string
}> {
    const response = await fetch(`${API_CONFIG.BASE_URL}/api/cosmosdb/store`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    })

    if (!response.ok) {
        let errorMessage = `Cosmos DB storage failed: ${response.statusText}`
        try {
            const errorData = await response.json()
            if (errorData.error) {
                errorMessage = errorData.error
            }
        } catch {
            // Use default error message
        }
        throw new Error(errorMessage)
    }

    const result = CosmosStoreResponseSchema.parse(await response.json())

    return {
        documentId: result.documentId || result.id || '',
        status: result.status,
        createdAt: result.createdAt,
        message: result.message,
    }
}

// ----- React Query Hooks -----

// Query key factory
export const queryKeys = {
    status: ['status'] as const,
    document: (id: string) => ['document', id] as const,
}

// Hook to check Azure status
export function useAzureStatus() {
    return useQuery({
        queryKey: queryKeys.status,
        queryFn: checkAzureStatus,
        staleTime: 60 * 1000, // Cache for 1 minute
        retry: 1,
    })
}

// Hook for file upload
export function useUploadDocument() {
    return useMutation({
        mutationFn: uploadToAzureBlob,
        onError: (error: Error) => {
            toast.error(`Upload failed: ${error.message}`)
        },
    })
}

// Hook for document analysis
export function useAnalyzeDocument() {
    return useMutation({
        mutationFn: analyzeDocument,
        onError: (error: Error) => {
            toast.error(`Analysis failed: ${error.message}`)
        },
    })
}

// Hook for data transformation
export function useTransformData() {
    return useMutation({
        mutationFn: transformToStructuredData,
        onError: (error: Error) => {
            toast.error(`Transformation failed: ${error.message}`)
        },
    })
}

// Hook for compliance check
export function useComplianceCheck() {
    return useMutation({
        mutationFn: performComplianceCheck,
        onError: (error: Error) => {
            toast.error(`Compliance check failed: ${error.message}`)
        },
    })
}

// Combined hook for full document processing pipeline
export function useDocumentProcessing() {
    const upload = useUploadDocument()
    const analyze = useAnalyzeDocument()
    const transform = useTransformData()
    const compliance = useComplianceCheck()

    const isProcessing = upload.isPending || analyze.isPending || transform.isPending || compliance.isPending

    return {
        upload,
        analyze,
        transform,
        compliance,
        isProcessing,
    }
}
