import { useState, useEffect } from 'react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  CloudArrowUp,
  Database,
  ScanSmiley,
  TextAlignLeft,
  ShieldCheck,
  UserCheck,
  PaperPlaneTilt,
  ChartBar,
  CheckCircle,
  Clock,
  LockSimple,
  ArrowRight,
  X,
  Check,
  Play,
  Pause,
  Warning,
} from '@phosphor-icons/react'
import { toast } from 'sonner'
import { BlobServiceClient } from '@azure/storage-blob'
import { AzureKeyCredential, DocumentAnalysisClient } from '@azure/ai-form-recognizer'

type StageStatus = 'inactive' | 'active' | 'processing' | 'completed'

type WorkflowMode = 'manual' | 'automated'

type DocumentData = {
  fileName: string
  fileUrl: string
  fileType?: string
  blobUrl?: string
  rawData?: Record<string, { value: string; confidence: number }>
  structuredData?: CustomsDeclaration
  confidenceScores?: ConfidenceScores
}

type CustomsDeclaration = {
  shipper: string
  receiver: string
  goodsDescription: string
  value: string
  countryOfOrigin: string
  hsCode: string
  weight: string
}

// Backend response format with per-field confidence
type StructuredDataWithConfidence = {
  shipper: { value: string; confidence: number }
  receiver: { value: string; confidence: number }
  goodsDescription: { value: string; confidence: number }
  value: { value: string; confidence: number }
  countryOfOrigin: { value: string; confidence: number }
  hsCode: { value: string; confidence: number }
  weight: { value: string; confidence: number }
}

// Helper to extract values from structured data with confidence
function extractValuesFromStructuredData(data: StructuredDataWithConfidence | CustomsDeclaration): CustomsDeclaration {
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

type ConfidenceScores = {
  ocrConfidence: number
  structureConfidence: number
  complianceConfidence: number
  overallConfidence: number
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:5000'

const AZURE_CONFIG = {
  storageConnectionString: import.meta.env.VITE_AZURE_STORAGE_CONNECTION_STRING || '',
  storageContainerName: import.meta.env.VITE_AZURE_STORAGE_CONTAINER || 'customs-documents',
  contentUnderstandingEndpoint: import.meta.env.VITE_AZURE_CONTENT_UNDERSTANDING_ENDPOINT || '',
}

// Check backend status for Azure configuration
const checkAzureStatus = async (): Promise<boolean> => {
  try {
    const response = await fetch(`${API_BASE}/api/status`)
    if (response.ok) {
      const data = await response.json()
      return data.azureConfigured && data.openaiConfigured
    }
  } catch (e) {
    console.warn('Could not check backend status, falling back to env vars')
  }
  // Fallback to env var check
  return !!(
    AZURE_CONFIG.storageConnectionString &&
    AZURE_CONFIG.contentUnderstandingEndpoint
  )
}

const mockRawData: Record<string, any> = {
  'SHIPPER NAME': { value: 'Global Electronics Ltd.', confidence: 0.98 },
  'SHIPPER ADDRESS': { value: '123 Tech Park, San Jose, CA 95110', confidence: 0.95 },
  'RECEIVER NAME': { value: 'European Distribution Center', confidence: 0.97 },
  'RECEIVER ADDRESS': { value: 'Hauptstrasse 45, 10115 Berlin, Germany', confidence: 0.94 },
  'GOODS': { value: 'Electronic Components - Semiconductors', confidence: 0.89 },
  'TOTAL VALUE': { value: '$45,850 USD', confidence: 0.92 },
  'ORIGIN': { value: 'United States', confidence: 0.99 },
  'WEIGHT': { value: '125 KG', confidence: 0.96 },
  'HS CODE': { value: '8542.31', confidence: 0.87 },
}

const mockStructuredData: CustomsDeclaration = {
  shipper: 'Global Electronics Ltd.',
  receiver: 'European Distribution Center',
  goodsDescription: 'Electronic Components - Semiconductors',
  value: '45850.00 USD',
  countryOfOrigin: 'United States',
  hsCode: '8542.31',
  weight: '125 KG',
}

const mockConfidenceScores: ConfidenceScores = {
  ocrConfidence: 0.94,
  structureConfidence: 0.91,
  complianceConfidence: 0.88,
  overallConfidence: 0.91,
}

async function uploadToAzureBlob(file: File): Promise<string> {
  // Always use backend API for uploads
  const formData = new FormData()
  formData.append('file', file)

  try {
    const response = await fetch(`${API_BASE}/api/upload`, {
      method: 'POST',
      body: formData,
    })

    if (!response.ok) {
      throw new Error(`Upload failed: ${response.statusText}`)
    }

    const data = await response.json()
    return data.blob_url || data.url
  } catch (error) {
    console.error('Error uploading file:', error)
    toast.error('Failed to upload file')
    throw error
  }
}

async function analyzeDocumentWithAI(blobUrl: string): Promise<{
  rawData: Record<string, { value: string; confidence: number }>
  structuredData: StructuredDataWithConfidence | null
  ocrConfidence: number
}> {
  // Use backend API for OCR + Field Extraction
  try {
    console.log('Calling OCR API with URL:', blobUrl)
    const response = await fetch(`${API_BASE}/api/ocr/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ blob_url: blobUrl })
    })

    console.log('OCR API response status:', response.status)

    if (response.ok) {
      const result = await response.json()
      console.log('OCR API result:', result)

      // Check if structured data was extracted (new flow)
      const hasStructuredData = result.structured_data &&
        Object.values(result.structured_data).some((field: unknown) => {
          const f = field as { value?: string }
          return f?.value
        })

      if (hasStructuredData) {
        return {
          rawData: result.raw_data || {},
          structuredData: result.structured_data as StructuredDataWithConfidence,
          ocrConfidence: result.ocr_confidence || 0.94,
        }
      } else if (result.raw_data && Object.keys(result.raw_data).length > 0) {
        // Fallback to old format (raw_data only)
        return {
          rawData: result.raw_data,
          structuredData: null,
          ocrConfidence: result.ocr_confidence || 0.94,
        }
      } else {
        console.warn('OCR returned empty data, using mock')
      }
    } else {
      const errorText = await response.text()
      console.warn('OCR API error:', response.status, errorText)
    }
  } catch (error) {
    console.warn('OCR API not available, using mock data:', error)
  }

  // Fallback to mock data
  console.log('Using mock OCR data')
  return {
    rawData: mockRawData,
    structuredData: null,
    ocrConfidence: 0.94,
  }
}

async function transformToStructuredData(
  rawData: Record<string, { value: string; confidence: number }>
): Promise<{ structuredData: CustomsDeclaration; structureConfidence: number }> {
  // Try backend API first
  try {
    const response = await fetch(`${API_BASE}/api/transform/structure`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_data: rawData })
    })

    if (response.ok) {
      const result = await response.json()
      // Extract plain values from the per-field confidence format
      const structuredData = extractValuesFromStructuredData(result.structured_data)
      return {
        structuredData,
        structureConfidence: result.structure_confidence
      }
    }
  } catch (error) {
    console.log('Backend not available, using mock data')
  }

  // Fallback to mock data
  let totalConfidence = 0
  let fieldCount = 0
  for (const [_, data] of Object.entries(rawData)) {
    totalConfidence += data.confidence
    fieldCount++
  }
  const structureConfidence = fieldCount > 0 ? totalConfidence / fieldCount : 0.91

  return {
    structuredData: mockStructuredData,
    structureConfidence: structureConfidence || 0.91,
  }
}

async function performComplianceCheck(
  data: CustomsDeclaration
): Promise<{ checks: boolean[]; complianceConfidence: number; issueDescriptions: string[] }> {
  // Try backend API first
  try {
    const response = await fetch(`${API_BASE}/api/compliance/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ structured_data: data })
    })

    if (response.ok) {
      const result = await response.json()
      return {
        checks: result.checks || [true, true, true, true, true],
        complianceConfidence: result.compliance_confidence || 0.88,
        issueDescriptions: result.issue_descriptions || [],
      }
    }
  } catch (error) {
    console.log('Backend compliance API not available, using mock data')
  }

  // Fallback to mock compliance check (simulates passing all checks)
  return {
    checks: [true, true, true, true, true],
    complianceConfidence: 0.88,
    issueDescriptions: [
      'HS code format validated successfully',
      'No country restrictions or embargoes apply',
      'Declared value is reasonable for goods type',
      'Shipper information verified and complete',
      'All required fields present and properly formatted'
    ],
  }
}

function App() {
  const [workflowMode, setWorkflowMode] = useState<WorkflowMode>('manual')
  const [isAutomatedRunning, setIsAutomatedRunning] = useState(false)
  const [currentStage, setCurrentStage] = useState(0)
  const [stageStatuses, setStageStatuses] = useState<StageStatus[]>([
    'active',
    'inactive',
    'inactive',
    'inactive',
    'inactive',
    'inactive',
    'inactive',
    'inactive',
  ])
  const [document, setDocument] = useState<DocumentData | null>(null)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [isDragging, setIsDragging] = useState(false)
  const [showScanLine, setShowScanLine] = useState(false)
  const [showRawData, setShowRawData] = useState(false)
  const [showStructuredData, setShowStructuredData] = useState(false)
  const [complianceChecks, setComplianceChecks] = useState<boolean[]>([])
  const [complianceDescriptions, setComplianceDescriptions] = useState<string[]>([])
  const [showApproval, setShowApproval] = useState(false)
  const [showReview, setShowReview] = useState(false)
  const [editedData, setEditedData] = useState<CustomsDeclaration>(mockStructuredData)
  const [showSubmitAnimation, setShowSubmitAnimation] = useState(false)
  const [azureConfigured, setAzureConfigured] = useState(false)
  const [statusLoading, setStatusLoading] = useState(true)

  useEffect(() => {
    checkAzureStatus().then(configured => {
      setAzureConfigured(configured)
      setStatusLoading(false)
    })
  }, [])

  const stages = [
    { name: 'Upload Document', icon: CloudArrowUp, label: 'Document Intake' },
    { name: 'Azure Storage', icon: Database, label: 'Data Collection' },
    { name: 'OCR + Transformation', icon: ScanSmiley, label: 'Content Understanding' },
    { name: 'Customs Fields', icon: TextAlignLeft, label: 'Declaration Data' },
    { name: 'Compliance Check', icon: ShieldCheck, label: 'Automated Validation' },
    { name: 'Approval Workflow', icon: UserCheck, label: 'Human Review' },
    { name: 'Customs Submission', icon: PaperPlaneTilt, label: 'Authority Filing' },
    { name: 'Fabric Storage', icon: ChartBar, label: 'Analytics Store' },
  ]

  const updateStageStatus = (index: number, status: StageStatus) => {
    setStageStatuses((prev) => {
      const newStatuses = [...prev]
      newStatuses[index] = status
      return newStatuses
    })
  }

  const advanceToStage = (index: number) => {
    setCurrentStage(index)
    updateStageStatus(index, 'active')
  }

  const resetWorkflow = () => {
    setCurrentStage(0)
    setStageStatuses([
      'active',
      'inactive',
      'inactive',
      'inactive',
      'inactive',
      'inactive',
      'inactive',
      'inactive',
    ])
    setDocument(null)
    setUploadProgress(0)
    setShowScanLine(false)
    setShowRawData(false)
    setShowStructuredData(false)
    setComplianceChecks([])
    setComplianceDescriptions([])
    setShowApproval(false)
    setShowReview(false)
    setShowSubmitAnimation(false)
    setIsAutomatedRunning(false)
  }

  const handleModeChange = (mode: string) => {
    setWorkflowMode(mode as WorkflowMode)
    resetWorkflow()
  }

  const handleFileUpload = (file: File) => {
    setUploadProgress(0)
    updateStageStatus(0, 'processing')

    const interval = setInterval(() => {
      setUploadProgress((prev) => {
        if (prev >= 100) {
          clearInterval(interval)
          const fileUrl = URL.createObjectURL(file)
          setDocument({
            fileName: file.name,
            fileUrl: fileUrl,
            fileType: file.type,
          })
          updateStageStatus(0, 'completed')
          advanceToStage(1)

          if (workflowMode === 'automated' && isAutomatedRunning) {
            setTimeout(() => handleStoreInAzure(file), 800)
          }
          return 100
        }
        return prev + 10
      })
    }, 100)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files[0]
    if (file && (file.type.startsWith('image/') || file.type === 'application/pdf')) {
      handleFileUpload(file)
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      handleFileUpload(file)
    }
  }

  const handleStoreInAzure = async (file?: File) => {
    updateStageStatus(1, 'processing')

    if (!document && !file) {
      toast.error('No document to store')
      return
    }

    try {
      const fileToUpload = file || (document ? await fetch(document.fileUrl).then(r => r.blob()).then(b => new File([b], document.fileName)) : null)

      if (!fileToUpload) {
        throw new Error('No file available')
      }

      const blobUrl = await uploadToAzureBlob(fileToUpload)

      if (document) {
        setDocument({ ...document, blobUrl })
      } else if (file) {
        setDocument(prev => prev ? { ...prev, blobUrl } : null)
      }

      updateStageStatus(1, 'completed')
      advanceToStage(2)

      if (workflowMode === 'automated' && isAutomatedRunning) {
        setTimeout(() => handleRunOCR(blobUrl), 800)
      }
    } catch (error) {
      updateStageStatus(1, 'active')
      console.error('Storage error:', error)
    }
  }

  const handleRunOCR = async (blobUrl?: string) => {
    updateStageStatus(2, 'processing')
    setShowScanLine(true)

    const urlToAnalyze = blobUrl || document?.blobUrl || document?.fileUrl

    if (!urlToAnalyze) {
      toast.error('No document URL available')
      setShowScanLine(false)
      return
    }

    try {
      const { rawData, structuredData, ocrConfidence } = await analyzeDocumentWithAI(urlToAnalyze)

      setTimeout(() => {
        setShowScanLine(false)
        setShowRawData(true)

        // If we got structured data from OCR, we can skip the LLM transform step
        const hasStructuredData = structuredData &&
          Object.values(structuredData).some(field => field?.value)

        if (document) {
          const extractedStructuredData = hasStructuredData
            ? extractValuesFromStructuredData(structuredData)
            : undefined

          setDocument({
            ...document,
            rawData,
            structuredData: extractedStructuredData,
            confidenceScores: {
              ocrConfidence,
              structureConfidence: hasStructuredData ? ocrConfidence : 0,
              complianceConfidence: 0,
              overallConfidence: ocrConfidence,
            },
          })

          if (extractedStructuredData) {
            setEditedData(extractedStructuredData)
            setShowStructuredData(true)
          }
        }

        updateStageStatus(2, 'completed')
        advanceToStage(3)

        if (workflowMode === 'automated' && isAutomatedRunning) {
          if (hasStructuredData) {
            // Content Understanding extracted structured data - go to compliance
            setTimeout(() => {
              handleDataTransformComplete()
            }, 800)
          } else {
            // Need LLM transform for raw data (fallback)
            setTimeout(() => handleTransformData(rawData), 800)
          }
        }
      }, 1500)
    } catch (error) {
      setShowScanLine(false)
      updateStageStatus(2, 'active')
      console.error('OCR error:', error)
    }
  }

  const handleTransformData = async (rawDataParam?: Record<string, { value: string; confidence: number }>) => {
    updateStageStatus(3, 'processing')

    const dataToTransform = rawDataParam || document?.rawData

    if (!dataToTransform) {
      toast.error('No data to transform')
      return
    }

    try {
      const { structuredData, structureConfidence } = await transformToStructuredData(dataToTransform)

      setTimeout(() => {
        setShowStructuredData(true)

        if (document) {
          const updatedScores = {
            ...document.confidenceScores!,
            structureConfidence,
            overallConfidence: 0,
          }
          updatedScores.overallConfidence = calculateOverallConfidence(updatedScores)

          setDocument({
            ...document,
            structuredData,
            confidenceScores: updatedScores,
          })
          setEditedData(structuredData)
        }

        updateStageStatus(3, 'completed')
        advanceToStage(3)

        if (workflowMode === 'automated' && isAutomatedRunning) {
          setTimeout(() => handleDataTransformComplete(), 800)
        }
      }, 1000)
    } catch (error) {
      updateStageStatus(3, 'active')
      console.error('Transform error:', error)
    }
  }

  const handleDataTransformComplete = () => {
    updateStageStatus(3, 'completed')
    advanceToStage(4)

    if (workflowMode === 'automated' && isAutomatedRunning) {
      setTimeout(() => handleComplianceCheck(), 800)
    }
  }

  const handleComplianceCheck = async () => {
    if (!document?.structuredData) {
      toast.error('No structured data available')
      return
    }

    updateStageStatus(4, 'processing')
    setComplianceChecks([])
    setComplianceDescriptions([])

    try {
      const { checks, complianceConfidence, issueDescriptions } = await performComplianceCheck(document.structuredData)

      checks.forEach((_, index) => {
        setTimeout(() => {
          setComplianceChecks((prev) => [...prev, checks[index]])
          setComplianceDescriptions((prev) => [...prev, issueDescriptions[index] || ''])
          if (index === checks.length - 1) {
            setTimeout(() => {
              if (document.confidenceScores) {
                const updatedScores = {
                  ...document.confidenceScores,
                  complianceConfidence,
                  overallConfidence: 0,
                }
                updatedScores.overallConfidence = calculateOverallConfidence(updatedScores)

                setDocument({
                  ...document,
                  confidenceScores: updatedScores,
                })
              }

              updateStageStatus(4, 'completed')
              advanceToStage(5)
              setShowApproval(true)

              if (workflowMode === 'automated' && isAutomatedRunning) {
                setTimeout(() => handleApprove(), 1200)
              }
            }, 300)
          }
        }, (index + 1) * 400)
      })
    } catch (error) {
      updateStageStatus(5, 'active')
      console.error('Compliance check error:', error)
    }
  }

  const handleApprove = () => {
    setShowApproval(false)
    updateStageStatus(6, 'completed')
    advanceToStage(7)

    if (workflowMode === 'automated' && isAutomatedRunning) {
      setTimeout(() => handleSubmitToCustoms(), 800)
    }
  }

  const handleReject = () => {
    setShowReview(true)
    setEditedData(document?.structuredData || mockStructuredData)
  }

  const handleManualApprove = () => {
    if (document) {
      setDocument({ ...document, structuredData: editedData })
    }
    setShowReview(false)
    setShowApproval(false)
    updateStageStatus(5, 'completed')
    advanceToStage(6)

    if (workflowMode === 'automated' && isAutomatedRunning) {
      setTimeout(() => handleSubmitToCustoms(), 800)
    }
  }

  const handleCancelReview = () => {
    setShowReview(false)
  }

  const handleSubmitToCustoms = () => {
    updateStageStatus(6, 'processing')
    setShowSubmitAnimation(true)
    setTimeout(() => {
      setShowSubmitAnimation(false)
      updateStageStatus(6, 'completed')
      advanceToStage(7)

      if (workflowMode === 'automated' && isAutomatedRunning) {
        setTimeout(() => handleStoreInFabric(), 800)
      }
    }, 2000)
  }

  const handleStoreInFabric = () => {
    updateStageStatus(7, 'processing')
    setTimeout(() => {
      updateStageStatus(7, 'completed')
      setIsAutomatedRunning(false)
    }, 1500)
  }

  const startAutomatedWorkflow = async () => {
    if (document) {
      resetWorkflow()
      await new Promise(resolve => setTimeout(resolve, 500))
    }

    setIsAutomatedRunning(true)

    const sampleImageBlob = await fetch('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iODAwIiBoZWlnaHQ9IjYwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iODAwIiBoZWlnaHQ9IjYwMCIgZmlsbD0iI2YzZjRmNiIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMjQiIGZpbGw9IiM0YTVhNjgiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGR5PSIuM2VtIj5DdXN0b21zIERlY2xhcmF0aW9uIERvY3VtZW50PC90ZXh0Pjwvc3ZnPg==').then(r => r.blob())
    const sampleFile = new File([sampleImageBlob], 'sample-customs-doc.svg', { type: 'image/svg+xml' })

    handleFileUpload(sampleFile)
  }

  const pauseAutomatedWorkflow = () => {
    setIsAutomatedRunning(false)
  }

  const getStatusBadge = (status: StageStatus) => {
    switch (status) {
      case 'inactive':
        return <Badge variant="outline" className="text-muted-foreground border-muted-foreground/30"><LockSimple className="w-3 h-3 mr-1" />Locked</Badge>
      case 'active':
        return <Badge className="bg-accent text-accent-foreground"><Clock className="w-3 h-3 mr-1" />Ready</Badge>
      case 'processing':
        return <Badge className="bg-processing text-white"><Clock className="w-3 h-3 mr-1 animate-spin" />Processing</Badge>
      case 'completed':
        return <Badge className="bg-success text-white"><CheckCircle className="w-3 h-3 mr-1" />Completed</Badge>
    }
  }

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.9) return 'text-success'
    if (confidence >= 0.8) return 'text-warning'
    return 'text-destructive'
  }

  const getConfidenceLabel = (confidence: number) => {
    if (confidence >= 0.9) return 'High'
    if (confidence >= 0.8) return 'Medium'
    return 'Low'
  }

  const calculateOverallConfidence = (scores: ConfidenceScores): number => {
    const validScores: number[] = []

    if (scores.ocrConfidence > 0) validScores.push(scores.ocrConfidence)
    if (scores.structureConfidence > 0) validScores.push(scores.structureConfidence)
    if (scores.complianceConfidence > 0) validScores.push(scores.complianceConfidence)

    if (validScores.length === 0) return 0

    return validScores.reduce((sum, score) => sum + score, 0) / validScores.length
  }

  const ConfidenceDisplay = ({ label, score }: { label: string; score: number }) => (
    <div className="flex items-center justify-between text-xs">
      <span className="text-muted-foreground">{label}</span>
      <div className="flex items-center gap-2">
        <div className="w-24 h-1.5 bg-muted rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-500 ${score >= 0.9 ? 'bg-success' : score >= 0.8 ? 'bg-warning' : 'bg-destructive'
              }`}
            style={{ width: `${score * 100}%` }}
          />
        </div>
        <span className={`font-mono font-medium ${getConfidenceColor(score)} min-w-[3rem] text-right`}>
          {(score * 100).toFixed(0)}%
        </span>
      </div>
    </div>
  )

  const DocumentPreview = ({ doc, showScanAnimation = false }: { doc: DocumentData; showScanAnimation?: boolean }) => {
    const isPdf = doc.fileType === 'application/pdf' || doc.fileName.toLowerCase().endsWith('.pdf')

    return (
      <div className="relative aspect-video rounded-lg overflow-hidden bg-muted">
        {isPdf ? (
          <object
            data={doc.fileUrl}
            type="application/pdf"
            className="w-full h-full"
          >
            <div className="flex items-center justify-center h-full bg-muted">
              <div className="text-center p-4">
                <div className="text-4xl mb-2">📄</div>
                <p className="text-sm text-muted-foreground">{doc.fileName}</p>
                <a
                  href={doc.fileUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-primary hover:underline mt-2 inline-block"
                >
                  Open PDF
                </a>
              </div>
            </div>
          </object>
        ) : (
          <img
            src={doc.fileUrl}
            alt={doc.fileName}
            className="w-full h-full object-cover"
          />
        )}
        {showScanAnimation && (
          <div className="absolute inset-0 overflow-hidden">
            <div className="absolute inset-x-0 h-0.5 bg-gradient-to-r from-transparent via-processing to-transparent scan-line" />
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      {!statusLoading && !azureConfigured && (
        <div className="bg-warning/10 border-b border-warning px-8 py-3">
          <div className="flex items-center gap-2 text-sm">
            <Warning size={20} className="text-warning" weight="fill" />
            <p className="text-foreground">
              <strong>Azure services not configured.</strong> Using mock data for demo. See README.md for configuration instructions.
            </p>
          </div>
        </div>
      )}
      <header className="border-b border-border bg-card backdrop-blur-sm sticky top-0 z-10 shadow-sm">
        <div className="px-8 py-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h1 className="text-3xl font-bold tracking-tight mb-2">
                Agentic AI Document Processing – Interactive Demo
              </h1>
              <p className="text-muted-foreground">
                Visual walkthrough of an AI-powered customs workflow
              </p>
            </div>
            {document?.confidenceScores && !isNaN(document.confidenceScores.overallConfidence) && document.confidenceScores.overallConfidence > 0 && (
              <Card className="px-4 py-3 min-w-[200px] shadow-md">
                <div className="text-xs font-semibold mb-2 text-muted-foreground uppercase tracking-wide">
                  Overall Confidence
                </div>
                <div className="flex items-center gap-2">
                  <div className={`text-2xl font-bold ${getConfidenceColor(document.confidenceScores.overallConfidence)}`}>
                    {(document.confidenceScores.overallConfidence * 100).toFixed(0)}%
                  </div>
                  <Badge variant="outline" className={getConfidenceColor(document.confidenceScores.overallConfidence)}>
                    {getConfidenceLabel(document.confidenceScores.overallConfidence)}
                  </Badge>
                </div>
              </Card>
            )}
          </div>

          <div className="flex items-center gap-4">
            <Tabs value={workflowMode} onValueChange={handleModeChange} className="w-auto">
              <TabsList>
                <TabsTrigger value="manual">Click Through Steps</TabsTrigger>
                <TabsTrigger value="automated">Automated Workflow</TabsTrigger>
              </TabsList>
            </Tabs>

            {workflowMode === 'automated' && (
              <div className="flex gap-2">
                {!isAutomatedRunning && currentStage < 7 && (
                  <Button onClick={startAutomatedWorkflow} size="sm">
                    <Play className="mr-2" size={16} />
                    {document ? 'Resume' : 'Start'} Automated
                  </Button>
                )}
                {isAutomatedRunning && (
                  <Button onClick={pauseAutomatedWorkflow} size="sm" variant="outline">
                    <Pause className="mr-2" size={16} />
                    Pause
                  </Button>
                )}
                {(document || currentStage > 0) && (
                  <Button onClick={resetWorkflow} size="sm" variant="outline">
                    Reset
                  </Button>
                )}
              </div>
            )}

            {workflowMode === 'manual' && document && currentStage > 0 && (
              <Button onClick={resetWorkflow} size="sm" variant="outline">
                Reset
              </Button>
            )}
          </div>
        </div>
      </header>

      <main className="p-8">
        <div className="max-w-4xl mx-auto">
          <div className="space-y-6">
            {stages.map((stage, index) => {
              const Icon = stage.icon
              const status = stageStatuses[index]
              const isActive = currentStage === index

              return (
                <div key={index} className="relative">
                  <Card
                    className={`transition-all duration-300 shadow-sm ${isActive ? 'ring-2 ring-accent shadow-md' : ''
                      } ${status === 'processing' ? 'pulse-glow' : ''} ${status === 'inactive' ? 'opacity-50' : ''
                      }`}
                  >
                    <div className="p-6 flex flex-col gap-4">
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-4">
                          <div className={`p-3 rounded-lg ${status === 'completed' ? 'bg-success/20 text-success' :
                            status === 'processing' ? 'bg-processing/20 text-processing' :
                              status === 'active' ? 'bg-accent/20 text-accent' :
                                'bg-muted text-muted-foreground'
                            }`}>
                            <Icon size={24} weight="duotone" />
                          </div>
                          <div>
                            <h3 className="font-semibold text-lg mb-1">{stage.name}</h3>
                            <p className="text-xs text-muted-foreground tracking-wide uppercase">
                              {stage.label}
                            </p>
                          </div>
                        </div>
                        {getStatusBadge(status)}
                      </div>

                      {index === 0 && status === 'active' && !document && workflowMode === 'manual' && (
                        <div
                          onDrop={handleDrop}
                          onDragOver={(e) => {
                            e.preventDefault()
                            setIsDragging(true)
                          }}
                          onDragLeave={() => setIsDragging(false)}
                          className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-all ${isDragging
                            ? 'border-accent bg-accent/10 scale-105'
                            : 'border-border hover:border-accent/50 hover:bg-accent/5'
                            }`}
                          onClick={() => window.document.getElementById('file-input')?.click()}
                        >
                          <CloudArrowUp size={32} className="mx-auto mb-2 text-accent" />
                          <p className="text-sm text-muted-foreground">
                            Drop file or click to upload
                          </p>
                          <input
                            id="file-input"
                            type="file"
                            accept="image/*,application/pdf"
                            onChange={handleFileSelect}
                            className="hidden"
                          />
                        </div>
                      )}

                      {index === 0 && status === 'processing' && (
                        <div className="space-y-2">
                          <Progress value={uploadProgress} className="h-2" />
                          <p className="text-xs text-center text-muted-foreground">
                            Uploading... {uploadProgress}%
                          </p>
                        </div>
                      )}

                      {index === 0 && document && (
                        <div className="space-y-2">
                          <DocumentPreview doc={document} />
                          <p className="text-xs text-muted-foreground truncate">
                            {document.fileName}
                          </p>
                        </div>
                      )}

                      {index === 1 && status === 'active' && document && (
                        <Button onClick={() => handleStoreInAzure()} className="w-full">
                          <Database className="mr-2" size={16} />
                          Store in Azure Storage
                        </Button>
                      )}

                      {index === 2 && status === 'active' && (
                        <Button onClick={() => handleRunOCR()} className="w-full">
                          <ScanSmiley className="mr-2" size={16} />
                          Run OCR
                        </Button>
                      )}

                      {index === 2 && document && showScanLine && (
                        <DocumentPreview doc={document} showScanAnimation={true} />
                      )}

                      {index === 2 && status === 'completed' && document?.confidenceScores && (
                        <div className="space-y-2 p-3 bg-muted/30 rounded-lg">
                          <ConfidenceDisplay
                            label="OCR Confidence"
                            score={document.confidenceScores.ocrConfidence}
                          />
                        </div>
                      )}

                      {index === 3 && showStructuredData && document?.structuredData && (
                        <div className="space-y-2">
                          <ScrollArea className="h-48 rounded-lg border border-border p-3 bg-muted/30">
                            <div className="space-y-2 font-mono text-xs">
                              <div className="text-accent">{'{'}</div>
                              {Object.entries(document.structuredData).map(([key, value], i) => (
                                <div key={i} className="stagger-fade-in pl-4" style={{ animationDelay: `${i * 150}ms` }}>
                                  <span className="text-processing">"{key}"</span>
                                  <span className="text-muted-foreground">: </span>
                                  <span className="text-success">"{value}"</span>
                                  {i < Object.keys(document.structuredData!).length - 1 && ','}
                                </div>
                              ))}
                              <div className="text-accent">{'}'}</div>
                            </div>
                          </ScrollArea>
                          {document.confidenceScores && (
                            <div className="p-3 bg-muted/30 rounded-lg space-y-2">
                              <ConfidenceDisplay
                                label="Extraction Confidence"
                                score={document.confidenceScores.structureConfidence}
                              />
                            </div>
                          )}
                          {status === 'active' && (
                            <Button onClick={handleDataTransformComplete} className="w-full" size="sm">
                              Continue
                              <ArrowRight className="ml-2" size={16} />
                            </Button>
                          )}
                        </div>
                      )}

                      {index === 4 && status === 'active' && complianceChecks.length === 0 && (
                        <Button onClick={handleComplianceCheck} className="w-full">
                          <ShieldCheck className="mr-2" size={16} />
                          Run Compliance Check
                        </Button>
                      )}

                      {index === 4 && complianceChecks.length > 0 && (
                        <div className="space-y-3">
                          <div className="space-y-2">
                            {[
                              'HS Code Validation',
                              'Country Restrictions',
                              'Value Declaration',
                              'Shipper Verification',
                              'Document Completeness',
                            ].map((check, i) => (
                              <div
                                key={i}
                                className="flex flex-col gap-1"
                              >
                                <div className="flex items-center gap-2 text-sm">
                                  {complianceChecks[i] !== undefined ? (
                                    complianceChecks[i] ? (
                                      <CheckCircle
                                        size={16}
                                        className="text-success check-bounce flex-shrink-0"
                                        weight="fill"
                                      />
                                    ) : (
                                      <Warning
                                        size={16}
                                        className="text-warning flex-shrink-0"
                                        weight="fill"
                                      />
                                    )
                                  ) : (
                                    <div className="w-4 h-4 border-2 border-muted rounded-full flex-shrink-0" />
                                  )}
                                  <span className={complianceChecks[i] !== undefined ? 'text-foreground font-medium' : 'text-muted-foreground'}>
                                    {check}
                                  </span>
                                </div>
                                {complianceDescriptions[i] && (
                                  <p className={`text-xs ml-6 ${complianceChecks[i] ? 'text-muted-foreground' : 'text-warning'}`}>
                                    {complianceDescriptions[i]}
                                  </p>
                                )}
                              </div>
                            ))}
                          </div>
                          {status === 'completed' && document?.confidenceScores && (
                            <div className="p-3 bg-muted/30 rounded-lg space-y-2">
                              <ConfidenceDisplay
                                label="Compliance Confidence"
                                score={document.confidenceScores.complianceConfidence}
                              />
                            </div>
                          )}
                        </div>
                      )}

                      {index === 5 && showApproval && (
                        <Card className="border-warning bg-warning/5 shadow-sm">
                          <div className="p-4 space-y-3">
                            <div className="flex items-center gap-2">
                              <UserCheck size={20} className="text-warning" weight="duotone" />
                              <span className="text-sm font-medium">Approval Required</span>
                            </div>
                            <p className="text-xs text-muted-foreground">
                              Document requires human verification before submission
                            </p>
                            <div className="flex gap-2">
                              <Button onClick={handleApprove} size="sm" className="flex-1 bg-success hover:bg-success/90 text-white">
                                <Check className="mr-1" size={16} />
                                Approve
                              </Button>
                              <Button onClick={handleReject} size="sm" variant="outline" className="flex-1">
                                <X className="mr-1" size={16} />
                                Reject
                              </Button>
                            </div>
                          </div>
                        </Card>
                      )}

                      {index === 6 && status === 'active' && (
                        <Button onClick={handleSubmitToCustoms} className="w-full">
                          <PaperPlaneTilt className="mr-2" size={16} />
                          Submit to Customs
                        </Button>
                      )}

                      {index === 6 && showSubmitAnimation && (
                        <div className="text-center py-4">
                          <div className="inline-block animate-bounce">
                            <PaperPlaneTilt size={48} className="text-processing" weight="duotone" />
                          </div>
                          <p className="text-sm text-muted-foreground mt-2">
                            Submitting to customs authority...
                          </p>
                        </div>
                      )}

                      {index === 7 && status === 'active' && (
                        <Button onClick={handleStoreInFabric} className="w-full">
                          <ChartBar className="mr-2" size={16} />
                          Store in Fabric
                        </Button>
                      )}

                      {index === 7 && status === 'completed' && (
                        <div className="text-center py-2">
                          <CheckCircle size={48} className="mx-auto text-success mb-2" weight="duotone" />
                          <p className="text-sm font-medium text-success">
                            Workflow Complete!
                          </p>
                          <p className="text-xs text-muted-foreground mt-1">
                            Document processed and stored
                          </p>
                        </div>
                      )}
                    </div>
                  </Card>

                  {index < stages.length - 1 && (
                    <div className="flex justify-center py-2">
                      <ArrowRight
                        size={28}
                        className={`transform rotate-90 transition-colors duration-300 ${stageStatuses[index] === 'completed'
                          ? 'text-success'
                          : 'text-muted-foreground'
                          }`}
                      />
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </main>

      <Dialog open={showReview} onOpenChange={(open) => {
        if (!open) {
          handleCancelReview()
        }
      }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Manual Review Required</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="shipper">Shipper</Label>
                <Input
                  id="shipper"
                  value={editedData.shipper}
                  onChange={(e) => setEditedData({ ...editedData, shipper: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="receiver">Receiver</Label>
                <Input
                  id="receiver"
                  value={editedData.receiver}
                  onChange={(e) => setEditedData({ ...editedData, receiver: e.target.value })}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="goods">Goods Description</Label>
              <Textarea
                id="goods"
                value={editedData.goodsDescription}
                onChange={(e) => setEditedData({ ...editedData, goodsDescription: e.target.value })}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="value">Value</Label>
                <Input
                  id="value"
                  value={editedData.value}
                  onChange={(e) => setEditedData({ ...editedData, value: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="weight">Weight</Label>
                <Input
                  id="weight"
                  value={editedData.weight}
                  onChange={(e) => setEditedData({ ...editedData, weight: e.target.value })}
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="country">Country of Origin</Label>
                <Input
                  id="country"
                  value={editedData.countryOfOrigin}
                  onChange={(e) => setEditedData({ ...editedData, countryOfOrigin: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="hscode">HS Code</Label>
                <Input
                  id="hscode"
                  value={editedData.hsCode}
                  onChange={(e) => setEditedData({ ...editedData, hsCode: e.target.value })}
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={handleCancelReview}>
              Cancel
            </Button>
            <Button onClick={handleManualApprove} className="bg-success hover:bg-success/90 text-white">
              <Check className="mr-2" size={16} />
              Approve Manually
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default App
