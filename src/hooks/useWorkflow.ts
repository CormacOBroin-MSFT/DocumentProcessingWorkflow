/**
 * Custom hook for managing workflow state
 * Centralizes stage management, loading states, and transitions
 */

import { useState, useCallback, useMemo } from 'react'
import type {
    StageStatus,
    StageStatusValue,
    WorkflowMode,
    AutomatedStep,
    ProcessingStep,
    CustomsDeclaration,
    ConfidenceScores,
    ComplianceIssue,
    StructuredDataWithConfidence,
} from '@/types/customs'
import { WORKFLOW_STAGES, CONFIDENCE_THRESHOLD } from '@/constants'

// ----- Workflow State Interface -----

export interface WorkflowState {
    // Mode and stage
    mode: WorkflowMode
    currentStage: number

    // Document data
    documentUrl: string | null
    documentFile: File | null
    rawExtractedText: Record<string, { value: string; confidence: number }>
    structuredData: CustomsDeclaration | null
    structuredDataWithConfidence: StructuredDataWithConfidence | null

    // Confidence scores
    confidenceScores: ConfidenceScores

    // Compliance
    complianceChecks: boolean[]
    complianceIssues: ComplianceIssue[]

    // Stage statuses
    stages: StageStatus[]

    // Automated workflow
    automatedStep: AutomatedStep
    processingSteps: ProcessingStep[]

    // UI state
    isProcessing: boolean
    error: string | null
}

export const initialWorkflowState: WorkflowState = {
    mode: 'manual',
    currentStage: 0,
    documentUrl: null,
    documentFile: null,
    rawExtractedText: {},
    structuredData: null,
    structuredDataWithConfidence: null,
    confidenceScores: {
        ocr: 0,
        structure: 0,
        compliance: 0,
    },
    complianceChecks: [],
    complianceIssues: [],
    stages: WORKFLOW_STAGES.map((stage) => ({
        name: stage.name,
        status: 'pending' as const,
    })),
    automatedStep: 'idle',
    processingSteps: [],
    isProcessing: false,
    error: null,
}

// ----- Hook Implementation -----

export function useWorkflow() {
    const [state, setState] = useState<WorkflowState>(initialWorkflowState)

    // ----- Mode Management -----

    const setMode = useCallback((mode: WorkflowMode) => {
        setState((prev) => ({
            ...prev,
            mode,
            // Reset stage on mode change
            currentStage: 0,
            automatedStep: 'idle',
            processingSteps: [],
        }))
    }, [])

    // ----- Stage Management -----

    const setCurrentStage = useCallback((stage: number) => {
        setState((prev) => {
            const stages: StageStatus[] = prev.stages.map((s, i) => ({
                ...s,
                status: i < stage ? 'complete' as const : i === stage ? 'in-progress' as const : s.status,
            }))
            return { ...prev, currentStage: stage, stages }
        })
    }, [])

    const updateStageStatus = useCallback(
        (stageIndex: number, status: StageStatusValue) => {
            setState((prev) => {
                const stages = [...prev.stages]
                if (stages[stageIndex]) {
                    stages[stageIndex] = { ...stages[stageIndex], status }
                }
                return { ...prev, stages }
            })
        },
        []
    )

    const markStageComplete = useCallback((stageIndex: number) => {
        updateStageStatus(stageIndex, 'complete')
    }, [updateStageStatus])

    // ----- Document Management -----

    const setDocument = useCallback((file: File | null, url: string | null) => {
        setState((prev) => ({
            ...prev,
            documentFile: file,
            documentUrl: url,
        }))
    }, [])

    const setRawExtractedText = useCallback(
        (data: Record<string, { value: string; confidence: number }>) => {
            setState((prev) => ({ ...prev, rawExtractedText: data }))
        },
        []
    )

    const setStructuredData = useCallback((data: CustomsDeclaration | null) => {
        setState((prev) => ({ ...prev, structuredData: data }))
    }, [])

    const setStructuredDataWithConfidence = useCallback(
        (data: StructuredDataWithConfidence | null) => {
            setState((prev) => ({ ...prev, structuredDataWithConfidence: data }))
        },
        []
    )

    const updateStructuredField = useCallback(
        (field: keyof CustomsDeclaration, value: string) => {
            setState((prev) => {
                if (!prev.structuredData) return prev
                return {
                    ...prev,
                    structuredData: { ...prev.structuredData, [field]: value },
                }
            })
        },
        []
    )

    // ----- Confidence Management -----

    const setConfidenceScores = useCallback((scores: Partial<ConfidenceScores>) => {
        setState((prev) => ({
            ...prev,
            confidenceScores: { ...prev.confidenceScores, ...scores },
        }))
    }, [])

    const overallConfidence = useMemo(() => {
        const { ocr, structure, compliance } = state.confidenceScores
        return (ocr + structure + compliance) / 3
    }, [state.confidenceScores])

    const needsReview = useMemo(() => {
        return overallConfidence < CONFIDENCE_THRESHOLD.MEDIUM
    }, [overallConfidence])

    // ----- Compliance Management -----

    const setComplianceChecks = useCallback((checks: boolean[]) => {
        setState((prev) => ({ ...prev, complianceChecks: checks }))
    }, [])

    const setComplianceIssues = useCallback((issues: ComplianceIssue[]) => {
        setState((prev) => ({ ...prev, complianceIssues: issues }))
    }, [])

    const updateComplianceIssue = useCallback(
        (index: number, updates: Partial<ComplianceIssue>) => {
            setState((prev) => {
                const issues = [...prev.complianceIssues]
                if (issues[index]) {
                    issues[index] = { ...issues[index], ...updates }
                }
                return { ...prev, complianceIssues: issues }
            })
        },
        []
    )

    // ----- Automated Workflow Management -----

    const setAutomatedStep = useCallback((step: AutomatedStep) => {
        setState((prev) => ({ ...prev, automatedStep: step }))
    }, [])

    const setProcessingSteps = useCallback((steps: ProcessingStep[]) => {
        setState((prev) => ({ ...prev, processingSteps: steps }))
    }, [])

    const updateProcessingStep = useCallback(
        (stepId: string, updates: Partial<ProcessingStep>) => {
            setState((prev) => {
                const steps = prev.processingSteps.map((step) =>
                    step.id === stepId ? { ...step, ...updates } : step
                )
                return { ...prev, processingSteps: steps }
            })
        },
        []
    )

    // ----- UI State Management -----

    const setIsProcessing = useCallback((isProcessing: boolean) => {
        setState((prev) => ({ ...prev, isProcessing }))
    }, [])

    const setError = useCallback((error: string | null) => {
        setState((prev) => ({ ...prev, error }))
    }, [])

    // ----- Reset Functions -----

    const resetWorkflow = useCallback(() => {
        setState(initialWorkflowState)
    }, [])

    const resetToStage = useCallback((stage: number) => {
        setState((prev) => ({
            ...prev,
            currentStage: stage,
            stages: WORKFLOW_STAGES.map((s, i): StageStatus => ({
                name: s.name,
                status: i < stage ? 'complete' : i === stage ? 'in-progress' : 'pending',
            })),
        }))
    }, [])

    return {
        // State
        state,
        overallConfidence,
        needsReview,

        // Mode
        setMode,

        // Stages
        setCurrentStage,
        updateStageStatus,
        markStageComplete,

        // Document
        setDocument,
        setRawExtractedText,
        setStructuredData,
        setStructuredDataWithConfidence,
        updateStructuredField,

        // Confidence
        setConfidenceScores,

        // Compliance
        setComplianceChecks,
        setComplianceIssues,
        updateComplianceIssue,

        // Automated
        setAutomatedStep,
        setProcessingSteps,
        updateProcessingStep,

        // UI
        setIsProcessing,
        setError,

        // Reset
        resetWorkflow,
        resetToStage,
    }
}

export type UseWorkflowReturn = ReturnType<typeof useWorkflow>
