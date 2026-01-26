/**
 * Main Application Component
 * Customs Document Processing Workflow
 */

import { useState, useEffect, useCallback, useMemo } from 'react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  CloudArrowUp,
  Database,
  ScanSmiley,
  TextAlignLeft,
  ShieldCheck,
  UserCheck,
  PaperPlaneTilt,
  CheckCircle,
  Clock,
  LockSimple,
  ArrowRight,
  Warning,
} from '@phosphor-icons/react'
import { toast } from 'sonner'

// Components
import ApprovalWorkflow from '@/components/ApprovalWorkflow'
import { DocumentPreview } from '@/components/DocumentPreview'
import { ProcessingStatus } from '@/components/ProcessingStatus'
import { FileUpload } from '@/components/FileUpload'
import { WorkflowComplete } from '@/components/WorkflowComplete'
import { ConfidenceDisplay, getConfidenceColor, getConfidenceLabel } from '@/components/ConfidenceDisplay'

// Hooks
import { useBlobUrl } from '@/hooks/useBlobUrl'

// API
import {
  useAzureStatus,
  uploadToAzureBlob,
  analyzeDocument,
  transformToStructuredData,
  performComplianceCheck,
} from '@/api/documents'

// Types and Constants
import type {
  CustomsDeclaration,
  StructuredDataWithConfidence,
  ConfidenceScores,
  ProcessingStep,
  WorkflowMode,
  AutomatedStep,
} from '@/types/customs'
import { extractValuesFromStructuredData, calculateOverallConfidence } from '@/types/customs'
import { WORKFLOW_STAGES } from '@/constants'

// ----- Types -----

type StageStatus = 'inactive' | 'active' | 'processing' | 'completed'

interface DocumentData {
  fileName: string
  fileUrl: string
  fileType?: string
  blobUrl?: string
  rawData?: Record<string, { value: string; confidence: number }>
  structuredData?: CustomsDeclaration
  confidenceScores?: ConfidenceScores
}

// ----- App Component -----

function App() {
  // Mode and workflow state
  const [workflowMode, setWorkflowMode] = useState<WorkflowMode>('manual')
  const [isAutomatedRunning, setIsAutomatedRunning] = useState(false)
  const [currentStage, setCurrentStage] = useState(0)
  const [stageStatuses, setStageStatuses] = useState<StageStatus[]>(
    WORKFLOW_STAGES.map((_, i) => (i === 0 ? 'active' : 'inactive'))
  )

  // Document state
  const [document, setDocument] = useState<DocumentData | null>(null)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [isDragging, setIsDragging] = useState(false)
  const { createUrl: createBlobUrl, clearUrl: clearBlobUrl } = useBlobUrl()

  // Processing state
  const [showScanLine, setShowScanLine] = useState(false)
  const [showRawData, setShowRawData] = useState(false)
  const [showStructuredData, setShowStructuredData] = useState(false)
  const [rawDataWithConfidence, setRawDataWithConfidence] = useState<StructuredDataWithConfidence | null>(null)

  // Compliance state
  const [complianceChecks, setComplianceChecks] = useState<boolean[]>([])
  const [complianceDescriptions, setComplianceDescriptions] = useState<string[]>([])

  // Approval state
  const [showApproval, setShowApproval] = useState(false)
  const [editedData, setEditedData] = useState<CustomsDeclaration | null>(null)
  const [reviewerNotes, setReviewerNotes] = useState('')
  const [approvalStatus, setApprovalStatus] = useState<'pending' | 'approved' | 'draft'>('pending')

  // Animation state
  const [showSubmitAnimation, setShowSubmitAnimation] = useState(false)

  // Automated workflow state
  const [automatedStep, setAutomatedStep] = useState<AutomatedStep>('idle')
  const [processingStatus, setProcessingStatus] = useState('')
  const [processingSteps, setProcessingSteps] = useState<ProcessingStep[]>([])

  // Azure status
  const { data: azureStatus, isLoading: statusLoading } = useAzureStatus()

  // Stage configuration
  const stages = useMemo(
    () => [
      { name: 'Upload Document', icon: CloudArrowUp, label: 'Document Intake' },
      { name: 'Azure Storage', icon: Database, label: 'Data Collection' },
      { name: 'Content Understanding', icon: ScanSmiley, label: 'OCR + Transformation' },
      { name: 'Customs Fields', icon: TextAlignLeft, label: 'Declaration Data' },
      { name: 'Compliance Check', icon: ShieldCheck, label: 'Automated Validation' },
      { name: 'Approval Workflow', icon: UserCheck, label: 'Human Review' },
      { name: 'Customs Submission', icon: PaperPlaneTilt, label: 'Authority Filing' },
      { name: 'CosmosDB', icon: Database, label: 'Analytics Store' },
    ],
    []
  )

  // ----- Stage Management -----

  const updateStageStatus = useCallback((index: number, status: StageStatus) => {
    setStageStatuses((prev) => {
      const newStatuses = [...prev]
      newStatuses[index] = status
      return newStatuses
    })
  }, [])

  const advanceToStage = useCallback(
    (index: number) => {
      setCurrentStage(index)
      updateStageStatus(index, 'active')
    },
    [updateStageStatus]
  )

  // ----- Reset Workflow -----

  const resetWorkflow = useCallback(() => {
    setCurrentStage(0)
    setStageStatuses(WORKFLOW_STAGES.map((_, i) => (i === 0 ? 'active' : 'inactive')))
    clearBlobUrl()
    setDocument(null)
    setUploadProgress(0)
    setShowScanLine(false)
    setShowRawData(false)
    setShowStructuredData(false)
    setComplianceChecks([])
    setComplianceDescriptions([])
    setShowApproval(false)
    setShowSubmitAnimation(false)
    setIsAutomatedRunning(false)
    setRawDataWithConfidence(null)
    setReviewerNotes('')
    setApprovalStatus('pending')
    setEditedData(null)
    setAutomatedStep('idle')
    setProcessingStatus('')
    setProcessingSteps([])

    // Scroll to top of page
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [clearBlobUrl])

  // ----- Mode Change -----

  const handleModeChange = useCallback(
    (mode: string) => {
      setWorkflowMode(mode as WorkflowMode)
      resetWorkflow()
    },
    [resetWorkflow]
  )

  // ----- Automated Workflow -----

  const runAutomatedWorkflow = useCallback(
    async (file: File) => {
      setAutomatedStep('processing')
      setIsAutomatedRunning(true)

      const steps: ProcessingStep[] = [
        { id: 'upload', label: 'Uploading to Azure Storage', status: 'pending' },
        { id: 'ocr', label: 'Extracting document content (OCR)', status: 'pending' },
        { id: 'transform', label: 'Transforming to customs fields', status: 'pending' },
        { id: 'compliance', label: 'Running compliance checks', status: 'pending' },
      ]
      setProcessingSteps(steps)

      try {
        // Step 1: Upload to Azure Storage
        setProcessingSteps((prev) =>
          prev.map((s) => (s.id === 'upload' ? { ...s, status: 'in-progress' } : s))
        )
        setProcessingStatus('Uploading document to Azure Storage...')

        const fileUrl = createBlobUrl(file)
        setDocument({
          fileName: file.name,
          fileUrl: fileUrl,
          fileType: file.type,
        })

        const blobUrl = await uploadToAzureBlob(file)
        setDocument((prev) => (prev ? { ...prev, blobUrl } : null))
        setProcessingSteps((prev) =>
          prev.map((s) => (s.id === 'upload' ? { ...s, status: 'complete' } : s))
        )

        // Step 2: OCR + Extraction
        setProcessingSteps((prev) =>
          prev.map((s) => (s.id === 'ocr' ? { ...s, status: 'in-progress' } : s))
        )
        setProcessingStatus('Extracting document content with AI...')

        const urlToAnalyze = blobUrl || fileUrl
        const { rawData, structuredData, ocrConfidence, fieldsExtracted, extractionWarning } = await analyzeDocument(urlToAnalyze)

        // Show warning if extraction had issues
        if (extractionWarning) {
          toast.warning(extractionWarning, { duration: 8000 })
        }

        const hasStructuredData =
          structuredData && Object.values(structuredData).some((field) => field?.value)
        if (structuredData) {
          setRawDataWithConfidence(structuredData)
        }

        // Mark OCR step with warning status if no fields were extracted
        const ocrStatus = fieldsExtracted === 0 ? 'warning' as const : 'complete' as const
        setProcessingSteps((prev) =>
          prev.map((s) => (s.id === 'ocr' ? { ...s, status: ocrStatus } : s))
        )

        // Step 3: Transform to structured data
        setProcessingSteps((prev) =>
          prev.map((s) => (s.id === 'transform' ? { ...s, status: 'in-progress' } : s))
        )
        setProcessingStatus('Transforming to customs declaration fields...')

        let finalStructuredData: CustomsDeclaration
        let structureConfidence: number

        if (hasStructuredData && structuredData) {
          finalStructuredData = extractValuesFromStructuredData(structuredData)
          structureConfidence = ocrConfidence
        } else {
          const result = await transformToStructuredData(rawData)
          finalStructuredData = result.structuredData
          structureConfidence = result.structureConfidence
        }

        setDocument((prev) =>
          prev
            ? {
              ...prev,
              rawData,
              structuredData: finalStructuredData,
              confidenceScores: {
                ocr: ocrConfidence,
                structure: structureConfidence,
                compliance: 0,
              },
            }
            : null
        )
        setEditedData(finalStructuredData)
        setProcessingSteps((prev) =>
          prev.map((s) => (s.id === 'transform' ? { ...s, status: 'complete' } : s))
        )

        // Step 4: Compliance Check
        setProcessingSteps((prev) =>
          prev.map((s) => (s.id === 'compliance' ? { ...s, status: 'in-progress' } : s))
        )
        setProcessingStatus('Running compliance validation...')

        const {
          checks,
          complianceConfidence,
          issueDescriptions,
        } = await performComplianceCheck(finalStructuredData)
        setComplianceChecks(checks)
        setComplianceDescriptions(issueDescriptions)

        setDocument((prev) =>
          prev
            ? {
              ...prev,
              confidenceScores: prev.confidenceScores
                ? {
                  ...prev.confidenceScores,
                  compliance: complianceConfidence,
                }
                : undefined,
            }
            : null
        )

        setProcessingSteps((prev) =>
          prev.map((s) => (s.id === 'compliance' ? { ...s, status: 'complete' } : s))
        )
        setProcessingStatus('Processing complete. Ready for review.')

        // Brief pause then show approval
        await new Promise((resolve) => setTimeout(resolve, 800))
        setAutomatedStep('approval')
        setShowApproval(true)
        toast.info('Document processed. Please review and approve.')
      } catch (error) {
        console.error('Automated workflow error:', error)
        setProcessingStatus(
          `Error: ${error instanceof Error ? error.message : 'Processing failed'}`
        )
        setProcessingSteps((prev) =>
          prev.map((s) => (s.status === 'in-progress' ? { ...s, status: 'error' } : s))
        )
        toast.error('Processing failed. Please try again.')
      }
    },
    [createBlobUrl]
  )

  // ----- File Upload Handlers -----

  const handleFileUpload = useCallback(
    (file: File) => {
      // In automated mode, use the streamlined workflow
      if (workflowMode === 'automated') {
        runAutomatedWorkflow(file)
        return
      }

      // Manual mode - step by step
      setUploadProgress(0)
      updateStageStatus(0, 'processing')

      const interval = setInterval(() => {
        setUploadProgress((prev) => {
          if (prev >= 100) {
            clearInterval(interval)
            const fileUrl = createBlobUrl(file)
            setDocument({
              fileName: file.name,
              fileUrl: fileUrl,
              fileType: file.type,
            })
            updateStageStatus(0, 'completed')
            advanceToStage(1)
            return 100
          }
          return prev + 10
        })
      }, 100)
    },
    [workflowMode, runAutomatedWorkflow, updateStageStatus, advanceToStage, createBlobUrl]
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
      const file = e.dataTransfer.files[0]
      if (file && (file.type.startsWith('image/') || file.type === 'application/pdf')) {
        handleFileUpload(file)
      }
    },
    [handleFileUpload]
  )

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) {
        handleFileUpload(file)
      }
    },
    [handleFileUpload]
  )

  // ----- Azure Storage -----

  const handleStoreInAzure = useCallback(
    async (file?: File) => {
      updateStageStatus(1, 'processing')

      if (!document && !file) {
        toast.error('No document to store')
        return
      }

      try {
        const fileToUpload =
          file ||
          (document
            ? await fetch(document.fileUrl)
              .then((r) => r.blob())
              .then((b) => new File([b], document.fileName))
            : null)

        if (!fileToUpload) {
          throw new Error('No file available')
        }

        const blobUrl = await uploadToAzureBlob(fileToUpload)

        if (document) {
          setDocument({ ...document, blobUrl })
        }

        updateStageStatus(1, 'completed')
        advanceToStage(2)

        if (workflowMode === 'automated' && isAutomatedRunning) {
          setTimeout(() => handleRunOCR(blobUrl), 800)
        }
      } catch (error) {
        updateStageStatus(1, 'active')
        console.error('Storage error:', error)
        toast.error('Failed to store document')
      }
    },
    [document, updateStageStatus, advanceToStage, workflowMode, isAutomatedRunning]
  )

  // ----- OCR Processing -----

  const handleRunOCR = useCallback(
    async (blobUrl?: string) => {
      updateStageStatus(2, 'processing')
      setShowScanLine(true)

      const urlToAnalyze = blobUrl || document?.blobUrl || document?.fileUrl

      if (!urlToAnalyze) {
        toast.error('No document URL available')
        setShowScanLine(false)
        return
      }

      try {
        const { rawData, structuredData, ocrConfidence, fieldsExtracted, extractionWarning } = await analyzeDocument(urlToAnalyze)

        // Show warning if extraction had issues
        if (extractionWarning) {
          toast.warning(extractionWarning, { duration: 8000 })
        }

        setTimeout(() => {
          setShowScanLine(false)
          setShowRawData(true)

          const hasStructuredData =
            structuredData && Object.values(structuredData).some((field) => field?.value)

          if (structuredData) {
            setRawDataWithConfidence(structuredData)
          }

          if (document) {
            const extractedStructuredData = hasStructuredData
              ? extractValuesFromStructuredData(structuredData)
              : undefined

            setDocument({
              ...document,
              rawData,
              structuredData: extractedStructuredData,
              confidenceScores: {
                ocr: ocrConfidence,
                structure: hasStructuredData ? ocrConfidence : 0,
                compliance: 0,
              },
            })

            if (extractedStructuredData) {
              setEditedData(extractedStructuredData)
              setShowStructuredData(true)
            } else if (fieldsExtracted === 0) {
              // No fields extracted - show empty form for manual entry
              toast.info('No fields could be extracted. You can enter the data manually.')
            }
          }

          updateStageStatus(2, 'completed')
          advanceToStage(3)

          if (workflowMode === 'automated' && isAutomatedRunning) {
            if (hasStructuredData) {
              setTimeout(() => handleDataTransformComplete(), 800)
            } else {
              setTimeout(() => handleTransformData(rawData), 800)
            }
          }
        }, 1500)
      } catch (error) {
        setShowScanLine(false)
        updateStageStatus(2, 'active')
        console.error('OCR error:', error)
        toast.error('OCR processing failed')
      }
    },
    [document, updateStageStatus, advanceToStage, workflowMode, isAutomatedRunning]
  )

  // ----- Data Transformation -----

  const handleTransformData = useCallback(
    async (rawDataParam?: Record<string, { value: string; confidence: number }>) => {
      updateStageStatus(3, 'processing')

      const dataToTransform = rawDataParam || document?.rawData

      if (!dataToTransform) {
        toast.error('No data to transform')
        return
      }

      try {
        const { structuredData, structureConfidence } =
          await transformToStructuredData(dataToTransform)

        setTimeout(() => {
          setShowStructuredData(true)

          if (document) {
            const updatedScores: ConfidenceScores = {
              ocr: document.confidenceScores?.ocr || 0,
              structure: structureConfidence,
              compliance: document.confidenceScores?.compliance || 0,
            }

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
        toast.error('Data transformation failed')
      }
    },
    [document, updateStageStatus, advanceToStage, workflowMode, isAutomatedRunning]
  )

  const handleDataTransformComplete = useCallback(() => {
    updateStageStatus(3, 'completed')
    advanceToStage(4)

    if (workflowMode === 'automated' && isAutomatedRunning) {
      setTimeout(() => handleComplianceCheck(), 800)
    }
  }, [updateStageStatus, advanceToStage, workflowMode, isAutomatedRunning])

  // ----- Compliance Check -----

  const handleComplianceCheck = useCallback(async () => {
    if (!document?.structuredData) {
      toast.error('No structured data available')
      return
    }

    updateStageStatus(4, 'processing')
    setComplianceChecks([])
    setComplianceDescriptions([])

    try {
      const { checks, complianceConfidence, issueDescriptions } = await performComplianceCheck(
        document.structuredData
      )

      checks.forEach((_, index) => {
        setTimeout(() => {
          setComplianceChecks((prev) => [...prev, checks[index]])
          setComplianceDescriptions((prev) => [...prev, issueDescriptions[index] || ''])
          if (index === checks.length - 1) {
            setTimeout(() => {
              if (document.confidenceScores) {
                const updatedScores: ConfidenceScores = {
                  ...document.confidenceScores,
                  compliance: complianceConfidence,
                }

                setDocument({
                  ...document,
                  confidenceScores: updatedScores,
                })
              }

              updateStageStatus(4, 'completed')
              advanceToStage(5)
              setShowApproval(true)

              if (workflowMode === 'automated' && isAutomatedRunning) {
                toast.info('Automated workflow paused for human approval')
              }
            }, 300)
          }
        }, (index + 1) * 400)
      })
    } catch (error) {
      updateStageStatus(5, 'active')
      console.error('Compliance check error:', error)
      toast.error('Compliance check failed')
    }
  }, [document, updateStageStatus, advanceToStage, workflowMode, isAutomatedRunning])

  // ----- Approval Handlers -----

  const handleApprovalComplete = useCallback(
    async (data: CustomsDeclaration, notes: string) => {
      if (document) {
        setDocument({
          ...document,
          structuredData: data,
          confidenceScores: {
            ocr: 1.0,
            structure: 1.0,
            compliance: 1.0,
          },
        })
      }
      setEditedData(data)
      setReviewerNotes(notes)
      setApprovalStatus('approved')
      setShowApproval(false)
      toast.success('Declaration approved and locked')

      // In automated mode, continue to submission
      if (workflowMode === 'automated') {
        setAutomatedStep('complete')
        setProcessingStatus('Submitting to customs authority...')
        await new Promise((resolve) => setTimeout(resolve, 1500))
        setProcessingStatus('Storing in analytics...')
        await new Promise((resolve) => setTimeout(resolve, 1000))
        setProcessingStatus('Workflow complete!')
        setIsAutomatedRunning(false)
        toast.success('Document submitted and stored successfully!')
        return
      }

      // Manual mode - continue with stages
      updateStageStatus(5, 'completed')
      advanceToStage(6)
      if (isAutomatedRunning) {
        setTimeout(() => handleSubmitToCustoms(), 800)
      }
    },
    [document, workflowMode, updateStageStatus, advanceToStage, isAutomatedRunning]
  )

  // Handle confidence updates from ApprovalWorkflow
  const handleConfidenceChange = useCallback(
    (ocr: number, compliance: number) => {
      if (document?.confidenceScores) {
        setDocument({
          ...document,
          confidenceScores: {
            ...document.confidenceScores,
            ocr,
            compliance,
          },
        })
      }
    },
    [document]
  )

  const handleSaveDraft = useCallback(
    (data: CustomsDeclaration, notes: string) => {
      if (document) {
        setDocument({ ...document, structuredData: data })
      }
      setEditedData(data)
      setReviewerNotes(notes)
      setApprovalStatus('draft')
      toast.info('Draft saved. Document remains in review.')
    },
    [document]
  )

  const handleReturnToAutomation = useCallback(
    (reason: string, comment: string) => {
      console.log('Returning to automation:', reason, comment)
      setShowApproval(false)

      if (workflowMode === 'automated') {
        setAutomatedStep('idle')
        setProcessingSteps([])
        setProcessingStatus('')
        setDocument(null)
        clearBlobUrl()
        toast.info(`Document returned: ${reason}. Please upload again.`)
        return
      }

      // Manual mode - go back to OCR stage
      updateStageStatus(5, 'inactive')
      updateStageStatus(4, 'inactive')
      updateStageStatus(3, 'inactive')
      updateStageStatus(2, 'active')
      setCurrentStage(2)
      setComplianceChecks([])
      setComplianceDescriptions([])
      toast.info(`Document returned to automation: ${reason}`)
    },
    [workflowMode, clearBlobUrl, updateStageStatus]
  )

  // ----- Submission Handlers -----

  const handleSubmitToCustoms = useCallback(() => {
    updateStageStatus(6, 'processing')
    setShowSubmitAnimation(true)
    setTimeout(() => {
      setShowSubmitAnimation(false)
      updateStageStatus(6, 'completed')
      advanceToStage(7)

      if (workflowMode === 'automated' && isAutomatedRunning) {
        setTimeout(() => handleStoreInCosmosDB(), 800)
      }
    }, 2000)
  }, [updateStageStatus, advanceToStage, workflowMode, isAutomatedRunning])

  const handleStoreInCosmosDB = useCallback(() => {
    updateStageStatus(7, 'processing')
    setTimeout(() => {
      updateStageStatus(7, 'completed')
      setIsAutomatedRunning(false)
    }, 1500)
  }, [updateStageStatus])

  // ----- Status Badge -----

  const getStatusBadge = useCallback((status: StageStatus) => {
    switch (status) {
      case 'inactive':
        return (
          <Badge variant="outline" className="text-muted-foreground border-muted-foreground/30">
            <LockSimple className="w-3 h-3 mr-1" />
            Locked
          </Badge>
        )
      case 'active':
        return (
          <Badge className="bg-accent text-accent-foreground">
            <Clock className="w-3 h-3 mr-1" />
            Ready
          </Badge>
        )
      case 'processing':
        return (
          <Badge className="bg-processing text-white">
            <Clock className="w-3 h-3 mr-1 animate-spin" />
            Processing
          </Badge>
        )
      case 'completed':
        return (
          <Badge className="bg-success text-white">
            <CheckCircle className="w-3 h-3 mr-1" />
            Completed
          </Badge>
        )
    }
  }, [])

  // Overall confidence
  const overallConfidence = useMemo(() => {
    if (!document?.confidenceScores) return 0
    return calculateOverallConfidence(document.confidenceScores)
  }, [document?.confidenceScores])

  // Default data for approval workflow
  const defaultStructuredData: CustomsDeclaration = useMemo(
    () => ({
      shipper: '',
      receiver: '',
      goodsDescription: '',
      value: '',
      countryOfOrigin: '',
      hsCode: '',
      weight: '',
    }),
    []
  )

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Azure Warning Banner */}
      {!statusLoading && !azureStatus?.configured && (
        <div className="bg-warning/10 border-b border-warning px-8 py-3">
          <div className="flex items-center gap-2 text-sm">
            <Warning size={20} className="text-warning" weight="fill" />
            <p className="text-foreground">
              <strong>Azure services not configured.</strong> See README.md for configuration
              instructions.
            </p>
          </div>
        </div>
      )}

      {/* Header */}
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
            {overallConfidence > 0 && (
              <Card className="px-4 py-3 min-w-[200px] shadow-md">
                <div className="text-xs font-semibold mb-2 text-muted-foreground uppercase tracking-wide">
                  Overall Confidence
                </div>
                <div className="flex items-center gap-2">
                  <div className={`text-2xl font-bold ${getConfidenceColor(overallConfidence)}`}>
                    {(overallConfidence * 100).toFixed(0)}%
                  </div>
                  <Badge variant="outline" className={getConfidenceColor(overallConfidence)}>
                    {getConfidenceLabel(overallConfidence)}
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

            {workflowMode === 'automated' && (document || automatedStep !== 'idle') && (
              <Button onClick={resetWorkflow} size="sm" variant="outline">
                Reset
              </Button>
            )}

            {workflowMode === 'manual' && document && currentStage > 0 && (
              <Button onClick={resetWorkflow} size="sm" variant="outline">
                Reset
              </Button>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className={`${workflowMode === 'automated' && automatedStep === 'approval' ? 'p-4 lg:p-6' : 'p-8'}`}>
        <div className={`mx-auto ${workflowMode === 'automated' && automatedStep === 'approval' ? 'max-w-none' : 'max-w-4xl'}`}>
          {/* Automated Workflow */}
          {workflowMode === 'automated' && (
            <div className="space-y-6">
              {/* Upload Step */}
              {(automatedStep === 'idle' || automatedStep === 'upload') && (
                <FileUpload
                  onFileSelect={handleFileUpload}
                  title="Upload Customs Document"
                  description="Upload a customs declaration document to begin automated processing"
                  inputId="auto-file-input"
                />
              )}

              {/* Processing Step */}
              {automatedStep === 'processing' && (
                <ProcessingStatus
                  status={processingStatus}
                  steps={processingSteps}
                  document={
                    document
                      ? {
                        fileUrl: document.fileUrl,
                        fileName: document.fileName,
                        fileType: document.fileType,
                      }
                      : null
                  }
                />
              )}

              {/* Approval Step - Side by Side Layout */}
              {automatedStep === 'approval' && showApproval && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 lg:gap-8">
                  {/* Left: Original Document */}
                  <div className="lg:sticky lg:top-24 lg:self-start">
                    <Card className="shadow-lg overflow-hidden">
                      <div className="px-4 py-2 border-b bg-muted/30">
                        <h3 className="font-semibold text-sm">Original Document</h3>
                        <p className="text-xs text-muted-foreground">
                          {document?.fileName || 'Uploaded document'}
                        </p>
                      </div>
                      <div className="p-2">
                        {document && (
                          <div className="w-full rounded-lg overflow-hidden border bg-white" style={{ height: 'calc(100vh - 200px)', minHeight: '400px' }}>
                            {document.fileType === 'application/pdf' ||
                              document.fileName?.toLowerCase().endsWith('.pdf') ? (
                              <iframe
                                src={`${document.fileUrl}#toolbar=1&navpanes=0&scrollbar=1&view=FitH`}
                                title={document.fileName}
                                className="w-full h-full border-0 bg-white"
                              />
                            ) : (
                              <img
                                src={document.fileUrl}
                                alt={document.fileName}
                                className="w-full h-full object-contain"
                              />
                            )}
                          </div>
                        )}
                      </div>
                    </Card>
                  </div>

                  {/* Right: Approval Workflow */}
                  <div className="space-y-6">
                    <ApprovalWorkflow
                      structuredData={document?.structuredData || editedData || defaultStructuredData}
                      rawDataWithConfidence={rawDataWithConfidence}
                      complianceChecks={complianceChecks}
                      complianceDescriptions={complianceDescriptions}
                      extractionConfidence={document?.confidenceScores?.ocr || 0}
                      complianceConfidence={document?.confidenceScores?.compliance || 0}
                      onApprove={handleApprovalComplete}
                      onSaveDraft={handleSaveDraft}
                      onReturnToAutomation={handleReturnToAutomation}
                      onConfidenceChange={handleConfidenceChange}
                      onCancel={() => {
                        setShowApproval(false)
                        setAutomatedStep('idle')
                        resetWorkflow()
                      }}
                    />
                  </div>
                </div>
              )}

              {/* Complete Step */}
              {automatedStep === 'complete' && <WorkflowComplete onReset={resetWorkflow} />}
            </div>
          )}

          {/* Manual Mode - Step by Step */}
          {workflowMode === 'manual' && (
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
                            <div
                              className={`p-3 rounded-lg ${status === 'completed'
                                ? 'bg-success/20 text-success'
                                : status === 'processing'
                                  ? 'bg-processing/20 text-processing'
                                  : status === 'active'
                                    ? 'bg-accent/20 text-accent'
                                    : 'bg-muted text-muted-foreground'
                                }`}
                            >
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

                        {/* Stage 0: Upload */}
                        {index === 0 && status === 'active' && !document && (
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
                            <DocumentPreview
                              fileUrl={document.fileUrl}
                              fileName={document.fileName}
                              fileType={document.fileType}
                            />
                            <p className="text-xs text-muted-foreground truncate">
                              {document.fileName}
                            </p>
                          </div>
                        )}

                        {/* Stage 1: Azure Storage */}
                        {index === 1 && status === 'active' && document && (
                          <Button onClick={() => handleStoreInAzure()} className="w-full">
                            <Database className="mr-2" size={16} />
                            Store in Azure Storage
                          </Button>
                        )}

                        {/* Stage 2: OCR */}
                        {index === 2 && status === 'active' && (
                          <Button onClick={() => handleRunOCR()} className="w-full">
                            <ScanSmiley className="mr-2" size={16} />
                            Run OCR
                          </Button>
                        )}

                        {index === 2 && document && showScanLine && (
                          <DocumentPreview
                            fileUrl={document.fileUrl}
                            fileName={document.fileName}
                            fileType={document.fileType}
                            showScanAnimation={true}
                          />
                        )}

                        {index === 2 && status === 'completed' && document?.confidenceScores && (
                          <div className="space-y-2 p-3 bg-muted/30 rounded-lg">
                            <ConfidenceDisplay
                              label="OCR Confidence"
                              score={document.confidenceScores.ocr}
                            />
                          </div>
                        )}

                        {/* Stage 3: Structured Data */}
                        {index === 3 && showStructuredData && document?.structuredData && (
                          <div className="space-y-2">
                            <ScrollArea className="h-48 rounded-lg border border-border p-3 bg-muted/30">
                              <div className="space-y-2 font-mono text-xs">
                                <div className="text-accent">{'{'}</div>
                                {Object.entries(document.structuredData).map(([key, value], i) => (
                                  <div
                                    key={i}
                                    className="stagger-fade-in pl-4"
                                    style={{ animationDelay: `${i * 150}ms` }}
                                  >
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
                                  score={document.confidenceScores.structure}
                                />
                              </div>
                            )}
                            {status === 'active' && (
                              <Button
                                onClick={handleDataTransformComplete}
                                className="w-full"
                                size="sm"
                              >
                                Continue
                                <ArrowRight className="ml-2" size={16} />
                              </Button>
                            )}
                          </div>
                        )}

                        {/* Stage 4: Compliance */}
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
                                <div key={i} className="flex flex-col gap-1">
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
                                    <span
                                      className={
                                        complianceChecks[i] !== undefined
                                          ? 'text-foreground font-medium'
                                          : 'text-muted-foreground'
                                      }
                                    >
                                      {check}
                                    </span>
                                  </div>
                                  {complianceDescriptions[i] && (
                                    <p
                                      className={`text-xs ml-6 ${complianceChecks[i]
                                        ? 'text-muted-foreground'
                                        : 'text-warning'
                                        }`}
                                    >
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
                                  score={document.confidenceScores.compliance}
                                />
                              </div>
                            )}
                          </div>
                        )}

                        {/* Stage 5: Approval */}
                        {index === 5 && showApproval && (
                          <ApprovalWorkflow
                            structuredData={
                              document?.structuredData || editedData || defaultStructuredData
                            }
                            rawDataWithConfidence={rawDataWithConfidence}
                            complianceChecks={complianceChecks}
                            complianceDescriptions={complianceDescriptions}
                            extractionConfidence={document?.confidenceScores?.ocr || 0}
                            complianceConfidence={document?.confidenceScores?.compliance || 0}
                            onApprove={handleApprovalComplete}
                            onSaveDraft={handleSaveDraft}
                            onReturnToAutomation={handleReturnToAutomation}
                            onConfidenceChange={handleConfidenceChange}
                            onCancel={() => setShowApproval(false)}
                          />
                        )}

                        {/* Stage 6: Submit */}
                        {index === 6 && status === 'active' && (
                          <Button onClick={handleSubmitToCustoms} className="w-full">
                            <PaperPlaneTilt className="mr-2" size={16} />
                            Submit to Customs
                          </Button>
                        )}

                        {index === 6 && showSubmitAnimation && (
                          <div className="text-center py-4">
                            <div className="inline-block animate-bounce">
                              <PaperPlaneTilt
                                size={48}
                                className="text-processing"
                                weight="duotone"
                              />
                            </div>
                            <p className="text-sm text-muted-foreground mt-2">
                              Submitting to customs authority...
                            </p>
                          </div>
                        )}

                        {/* Stage 7: CosmosDB Storage */}
                        {index === 7 && status === 'active' && (
                          <Button onClick={handleStoreInCosmosDB} className="w-full">
                            <Database className="mr-2" size={16} />
                            Store in CosmosDB
                          </Button>
                        )}

                        {index === 7 && status === 'completed' && (
                          <div className="text-center py-2">
                            <CheckCircle
                              size={48}
                              className="mx-auto text-success mb-2"
                              weight="duotone"
                            />
                            <p className="text-sm font-medium text-success">Workflow Complete!</p>
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
          )}
        </div>
      </main>
    </div>
  )
}

export default App
