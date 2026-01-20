import { useState, useMemo, useEffect, useRef } from 'react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Progress } from '@/components/ui/progress'
import {
    Warning,
    CheckCircle,
    Info,
    PencilSimple,
    ShieldCheck,
    Lock,
    ArrowCounterClockwise,
    FloppyDisk,
    Sparkle,
} from '@phosphor-icons/react'
import type {
    CustomsDeclaration,
    StructuredDataWithConfidence,
    ComplianceIssue,
} from '@/types/customs'
import { FIELD_LABELS, FIELD_HINTS, COMPLIANCE_TO_FIELD } from '@/constants'

export type ApprovalWorkflowProps = {
    documentId?: string
    structuredData: CustomsDeclaration
    rawDataWithConfidence?: StructuredDataWithConfidence | null
    complianceChecks: boolean[]
    complianceDescriptions: string[]
    extractionConfidence: number
    complianceConfidence: number
    onApprove: (data: CustomsDeclaration, reviewerNotes: string) => void
    onSaveDraft: (data: CustomsDeclaration, reviewerNotes: string) => void
    onReturnToAutomation: (reason: string, comment: string) => void
    onCancel: () => void
    onConfidenceChange?: (ocr: number, compliance: number) => void
}

// Compliance check names
const COMPLIANCE_CHECK_NAMES = [
    'HS Code Validation',
    'Country Restrictions',
    'Value Declaration',
    'Shipper Verification',
    'Document Completeness',
]

export function ApprovalWorkflow({
    documentId,
    structuredData,
    rawDataWithConfidence,
    complianceChecks,
    complianceDescriptions,
    extractionConfidence,
    complianceConfidence,
    onApprove,
    onSaveDraft,
    onReturnToAutomation,
    onCancel,
    onConfidenceChange,
}: ApprovalWorkflowProps) {
    // Editable data state
    const [editedData, setEditedData] = useState<CustomsDeclaration>(structuredData)
    const [reviewerNotes, setReviewerNotes] = useState('')
    const [returnReason, setReturnReason] = useState('')
    const [returnComment, setReturnComment] = useState('')
    const [showReturnDialog, setShowReturnDialog] = useState(false)

    // Track which fields have been manually edited
    const [editedFields, setEditedFields] = useState<Set<keyof CustomsDeclaration>>(new Set())

    // Track which issues have been explicitly approved/verified by the reviewer
    const [approvedFields, setApprovedFields] = useState<Set<keyof CustomsDeclaration>>(new Set())

    // Track initial issues - computed once on mount and when compliance checks change
    // but NOT when editedData changes (so cards don't disappear while editing)
    const [initialIssues, setInitialIssues] = useState<ComplianceIssue[] | null>(null)
    const hasInitializedRef = useRef(false)

    // Detect issues from compliance checks and data quality
    const computeIssues = (data: CustomsDeclaration): ComplianceIssue[] => {
        const detectedIssues: ComplianceIssue[] = []

        // Check for missing/empty fields
        const fields = Object.keys(data) as Array<keyof CustomsDeclaration>
        fields.forEach((field) => {
            const value = data[field]
            if (!value || value.trim() === '') {
                detectedIssues.push({
                    field,
                    type: 'missing',
                    title: `Missing ${FIELD_LABELS[field]}`,
                    description: `${FIELD_LABELS[field]} is required for customs processing.`,
                    hint: FIELD_HINTS[field],
                })
            }
        })

        // Check compliance failures
        complianceChecks.forEach((passed, index) => {
            if (!passed && complianceDescriptions[index]) {
                const fieldName = COMPLIANCE_TO_FIELD[index]
                const field = (fieldName || 'goodsDescription') as keyof CustomsDeclaration
                // Don't duplicate if we already have a missing field issue
                const alreadyHasIssue = detectedIssues.some(i => i.field === field)

                if (!alreadyHasIssue) {
                    detectedIssues.push({
                        field,
                        type: 'invalid',
                        title: COMPLIANCE_CHECK_NAMES[index],
                        description: complianceDescriptions[index],
                        hint: FIELD_HINTS[field] || 'Please review and correct this field.',
                        checkIndex: index,
                    })
                }
            }
        })

        // Check for low confidence fields (if we have confidence data)
        if (rawDataWithConfidence) {
            fields.forEach((field) => {
                const fieldData = rawDataWithConfidence[field]
                if (fieldData && fieldData.confidence < 0.7 && !detectedIssues.some(i => i.field === field)) {
                    detectedIssues.push({
                        field,
                        type: 'low_confidence',
                        title: `Low Confidence: ${FIELD_LABELS[field]}`,
                        description: `AI extraction confidence is ${(fieldData.confidence * 100).toFixed(0)}%. Please verify this value.`,
                        hint: FIELD_HINTS[field],
                    })
                }
            })
        }

        return detectedIssues
    }

    // Initialize issues once on mount (using useEffect instead of useMemo to set state)
    useEffect(() => {
        if (!hasInitializedRef.current) {
            hasInitializedRef.current = true
            setInitialIssues(computeIssues(structuredData))
        }
    }, []) // eslint-disable-line react-hooks/exhaustive-deps

    // Use initial issues for display, but track which are now resolved
    const issues = initialIssues || computeIssues(structuredData)

    // Fields with issues
    const fieldsWithIssues = useMemo(() => {
        return new Set(issues.map(i => i.field))
    }, [issues])

    // Get confidence for a field
    const getFieldConfidence = (field: keyof CustomsDeclaration): number | null => {
        if (rawDataWithConfidence && rawDataWithConfidence[field]) {
            return rawDataWithConfidence[field].confidence
        }
        return null
    }

    // Check if field was AI inferred (low confidence or empty in original)
    const isAiInferred = (field: keyof CustomsDeclaration): boolean => {
        const conf = getFieldConfidence(field)
        return conf !== null && conf < 0.8
    }

    // Handle field change
    const handleFieldChange = (field: keyof CustomsDeclaration, value: string) => {
        setEditedData(prev => ({ ...prev, [field]: value }))
        setEditedFields(prev => new Set(prev).add(field))
    }

    // Handle approving/verifying a field
    const handleApproveField = (field: keyof CustomsDeclaration) => {
        setApprovedFields(prev => new Set(prev).add(field))
    }

    // Check if an issue is resolved (either edited with value or explicitly approved)
    const isIssueResolved = (issue: ComplianceIssue): boolean => {
        const hasValue = !!editedData[issue.field]?.trim()
        const wasEdited = editedFields.has(issue.field)
        const wasApproved = approvedFields.has(issue.field)
        return (wasEdited && hasValue) || wasApproved
    }

    // Calculate adjusted confidence based on human verification
    const adjustedExtractionConfidence = useMemo(() => {
        const totalFields = Object.keys(editedData).length
        const verifiedFields = approvedFields.size + editedFields.size
        // Blend original confidence with human verification boost
        const verificationBoost = verifiedFields / totalFields
        return Math.min(1, extractionConfidence + (verificationBoost * (1 - extractionConfidence)))
    }, [extractionConfidence, approvedFields.size, editedFields.size, editedData])

    const adjustedComplianceConfidence = useMemo(() => {
        const totalIssues = issues.length
        if (totalIssues === 0) return complianceConfidence
        const resolvedIssues = issues.filter(i => isIssueResolved(i)).length
        // Blend original confidence with resolution boost
        const resolutionBoost = resolvedIssues / totalIssues
        return Math.min(1, complianceConfidence + (resolutionBoost * (1 - complianceConfidence)))
    }, [complianceConfidence, issues, approvedFields.size, editedFields.size])

    // Track previous confidence values to prevent infinite loops
    const prevConfidenceRef = useRef({ ocr: -1, compliance: -1 })

    // Notify parent when confidence changes (only from user interaction, not prop changes)
    useEffect(() => {
        const prev = prevConfidenceRef.current
        // Only notify if values actually changed and it's not the initial render
        if (
            onConfidenceChange &&
            prev.ocr !== -1 &&
            (Math.abs(prev.ocr - adjustedExtractionConfidence) > 0.001 ||
             Math.abs(prev.compliance - adjustedComplianceConfidence) > 0.001)
        ) {
            onConfidenceChange(adjustedExtractionConfidence, adjustedComplianceConfidence)
        }
        prevConfidenceRef.current = { ocr: adjustedExtractionConfidence, compliance: adjustedComplianceConfidence }
    }, [approvedFields.size, editedFields.size]) // Only trigger on user actions, not prop changes

    // Validation check
    const canApprove = useMemo(() => {
        // All required fields must have values
        const allFieldsFilled = Object.values(editedData).every(v => v && v.trim() !== '')
        // Reviewer notes required
        const hasNotes = reviewerNotes.trim().length > 0
        return allFieldsFilled && hasNotes
    }, [editedData, reviewerNotes])

    // Calculate review reason
    const reviewReason = useMemo(() => {
        const reasons: string[] = []
        if (issues.some(i => i.type === 'missing')) {
            reasons.push('missing mandatory fields')
        }
        if (issues.some(i => i.type === 'invalid')) {
            reasons.push('compliance validation issues')
        }
        if (issues.some(i => i.type === 'low_confidence')) {
            reasons.push('low AI extraction confidence')
        }
        if (reasons.length === 0) {
            return 'Standard human review required for customs declarations.'
        }
        return `This declaration requires review due to ${reasons.join(' and ')}.`
    }, [issues])

    const handleApprove = () => {
        if (canApprove) {
            onApprove(editedData, reviewerNotes)
        }
    }

    const handleSaveDraft = () => {
        onSaveDraft(editedData, reviewerNotes)
    }

    const handleReturnToAutomation = () => {
        if (returnReason) {
            onReturnToAutomation(returnReason, returnComment)
            setShowReturnDialog(false)
        }
    }

    return (
        <div className="space-y-6">
            {/* Header Section */}
            <Card className="border-warning/50 bg-gradient-to-r from-warning/5 to-transparent">
                <div className="p-6">
                    <div className="flex items-start justify-between mb-4">
                        <div>
                            <h2 className="text-xl font-semibold flex items-center gap-2">
                                <ShieldCheck className="text-warning" weight="duotone" size={24} />
                                Human Review Required – Customs Declaration
                            </h2>
                            {documentId && (
                                <p className="text-sm text-muted-foreground mt-1">
                                    Reference: {documentId}
                                </p>
                            )}
                        </div>
                        <Badge variant="outline" className="text-warning border-warning">
                            Pending Review
                        </Badge>
                    </div>

                    {/* Confidence Summary */}
                    <div className="grid grid-cols-2 gap-4 mb-4">
                        <div className="p-3 bg-background/50 rounded-lg">
                            <div className="text-xs text-muted-foreground mb-1 flex items-center justify-between">
                                <span>Extraction Confidence</span>
                                {adjustedExtractionConfidence > extractionConfidence && (
                                    <span className="text-success text-xs">+{((adjustedExtractionConfidence - extractionConfidence) * 100).toFixed(0)}%</span>
                                )}
                            </div>
                            <div className="flex items-center gap-2">
                                <Progress
                                    value={adjustedExtractionConfidence * 100}
                                    className="flex-1 h-2"
                                />
                                <span className={`text-sm font-medium ${adjustedExtractionConfidence < 0.7 ? 'text-warning' : 'text-success'}`}>
                                    {(adjustedExtractionConfidence * 100).toFixed(0)}%
                                </span>
                            </div>
                        </div>
                        <div className="p-3 bg-background/50 rounded-lg">
                            <div className="text-xs text-muted-foreground mb-1 flex items-center justify-between">
                                <span>Compliance Confidence</span>
                                {adjustedComplianceConfidence > complianceConfidence && (
                                    <span className="text-success text-xs">+{((adjustedComplianceConfidence - complianceConfidence) * 100).toFixed(0)}%</span>
                                )}
                            </div>
                            <div className="flex items-center gap-2">
                                <Progress
                                    value={adjustedComplianceConfidence * 100}
                                    className="flex-1 h-2"
                                />
                                <span className={`text-sm font-medium ${adjustedComplianceConfidence < 0.7 ? 'text-warning' : 'text-success'}`}>
                                    {(adjustedComplianceConfidence * 100).toFixed(0)}%
                                </span>
                            </div>
                        </div>
                    </div>

                    {/* Review Reason */}
                    <div className="p-3 bg-warning/10 border border-warning/20 rounded-lg">
                        <div className="flex items-start gap-2">
                            <Info size={16} className="text-warning mt-0.5 flex-shrink-0" />
                            <p className="text-sm text-foreground">{reviewReason}</p>
                        </div>
                    </div>
                </div>
            </Card>

            {/* Issue Cards Section */}
            {issues.length > 0 && (
                <div className="space-y-3">
                    <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                        Issues Requiring Attention ({issues.filter(i => !isIssueResolved(i)).length} of {issues.length} remaining)
                    </h3>
                    <div className="space-y-3">
                        {issues.map((issue, index) => {
                            const resolved = isIssueResolved(issue)
                            const wasApproved = approvedFields.has(issue.field)
                            const hasValue = editedData[issue.field]?.trim()
                            return (
                                <Card
                                    key={`${issue.field}-${index}`}
                                    className={resolved
                                        ? "border-success/30 bg-success/5"
                                        : "border-warning/30 bg-warning/5"
                                    }
                                >
                                    <div className="p-4">
                                        <div className="flex items-start gap-3">
                                            {resolved ? (
                                                <CheckCircle size={20} className="text-success flex-shrink-0 mt-0.5" weight="fill" />
                                            ) : (
                                                <Warning size={20} className="text-warning flex-shrink-0 mt-0.5" weight="fill" />
                                            )}
                                            <div className="flex-1 space-y-3">
                                                <div className="flex items-start justify-between">
                                                    <div>
                                                        <h4 className={`font-medium ${resolved ? 'text-success' : 'text-foreground'}`}>
                                                            {resolved ? `✓ ${issue.title} - Verified` : issue.title}
                                                        </h4>
                                                        <p className="text-sm text-muted-foreground mt-1">{issue.description}</p>
                                                    </div>
                                                    <div className="flex items-center gap-2">
                                                        {resolved ? (
                                                            <Badge variant="outline" className="text-success border-success text-xs">
                                                                {wasApproved ? 'Approved' : 'Corrected'}
                                                            </Badge>
                                                        ) : hasValue && (
                                                            <Button
                                                                size="sm"
                                                                variant="outline"
                                                                className="h-7 text-xs border-success text-success hover:bg-success hover:text-white"
                                                                onClick={() => handleApproveField(issue.field)}
                                                            >
                                                                <CheckCircle size={14} className="mr-1" />
                                                                Verify
                                                            </Button>
                                                        )}
                                                    </div>
                                                </div>

                                                {/* Inline edit field */}
                                                <div className="space-y-2">
                                                    <Label htmlFor={`issue-${index}`} className="text-sm">
                                                        {FIELD_LABELS[issue.field]}
                                                        {issue.type === 'missing' && !resolved && <span className="text-destructive ml-1">*</span>}
                                                    </Label>
                                                    <div className="flex gap-2">
                                                        <Input
                                                            id={`issue-${index}`}
                                                            value={editedData[issue.field]}
                                                            onChange={(e) => handleFieldChange(issue.field, e.target.value)}
                                                            placeholder={issue.hint}
                                                            className={`flex-1 ${resolved ? 'border-success' : !editedData[issue.field] ? 'border-warning' : ''}`}
                                                        />
                                                        {!resolved && hasValue && (
                                                            <Button
                                                                size="icon"
                                                                variant="ghost"
                                                                className="h-9 w-9 text-success hover:bg-success/10"
                                                                onClick={() => handleApproveField(issue.field)}
                                                                title="Verify this value is correct"
                                                            >
                                                                <CheckCircle size={18} weight="bold" />
                                                            </Button>
                                                        )}
                                                    </div>
                                                    <p className="text-xs text-muted-foreground">{issue.hint}</p>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </Card>
                            )
                        })}
                    </div>
                </div>
            )}

            {/* Full Declaration Form */}
            <Card>
                <div className="p-4 border-b">
                    <h3 className="font-semibold flex items-center gap-2">
                        <PencilSimple size={18} />
                        Declaration Details
                    </h3>
                    <p className="text-xs text-muted-foreground mt-1">
                        Fields with issues are highlighted. Click to edit any field.
                    </p>
                </div>
                <div className="p-4">
                    <div className="grid grid-cols-2 gap-4">
                        {(Object.keys(FIELD_LABELS) as Array<keyof CustomsDeclaration>).map((field) => {
                            const hasIssue = fieldsWithIssues.has(field)
                            const confidence = getFieldConfidence(field)
                            const inferred = isAiInferred(field)
                            const wasEdited = editedFields.has(field)

                            return (
                                <div key={field} className={`space-y-2 ${field === 'goodsDescription' ? 'col-span-2' : ''}`}>
                                    <div className="flex items-center justify-between">
                                        <Label htmlFor={field} className="text-sm flex items-center gap-2">
                                            {FIELD_LABELS[field]}
                                            {hasIssue && <Warning size={14} className="text-warning" weight="fill" />}
                                            {inferred && !hasIssue && (
                                                <Badge variant="outline" className="text-xs py-0 h-5 gap-1">
                                                    <Sparkle size={10} />
                                                    AI Inferred
                                                </Badge>
                                            )}
                                            {wasEdited && !hasIssue && (
                                                <CheckCircle size={14} className="text-success" weight="fill" />
                                            )}
                                        </Label>
                                        {confidence !== null && (
                                            <span className={`text-xs ${confidence < 0.7 ? 'text-warning' : 'text-muted-foreground'}`}>
                                                {(confidence * 100).toFixed(0)}%
                                            </span>
                                        )}
                                    </div>
                                    {field === 'goodsDescription' ? (
                                        <Textarea
                                            id={field}
                                            value={editedData[field]}
                                            onChange={(e) => handleFieldChange(field, e.target.value)}
                                            className={`min-h-[80px] ${hasIssue ? 'border-warning focus:border-warning' : ''}`}
                                            placeholder={FIELD_HINTS[field]}
                                        />
                                    ) : (
                                        <Input
                                            id={field}
                                            value={editedData[field]}
                                            onChange={(e) => handleFieldChange(field, e.target.value)}
                                            className={hasIssue ? 'border-warning focus:border-warning' : ''}
                                            placeholder={FIELD_HINTS[field]}
                                        />
                                    )}
                                </div>
                            )
                        })}
                    </div>
                </div>
            </Card>

            {/* Reviewer Notes */}
            <Card>
                <div className="p-4 border-b">
                    <h3 className="font-semibold">Reviewer Notes</h3>
                    <p className="text-xs text-muted-foreground mt-1">
                        Document your review decisions for audit purposes. This is required.
                    </p>
                </div>
                <div className="p-4">
                    <Textarea
                        value={reviewerNotes}
                        onChange={(e) => setReviewerNotes(e.target.value)}
                        placeholder="Example: Confirmed HS codes and country of origin with shipper. Declared value based on commercial invoice AWE-DOCKET-000473."
                        className={`min-h-[100px] ${!reviewerNotes.trim() ? 'border-warning' : ''}`}
                    />
                    {!reviewerNotes.trim() && (
                        <p className="text-xs text-warning mt-2 flex items-center gap-1">
                            <Warning size={12} weight="fill" />
                            Reviewer notes are required before approval
                        </p>
                    )}
                </div>
            </Card>

            {/* Return to Automation Dialog */}
            {showReturnDialog && (
                <Card className="border-muted">
                    <div className="p-4">
                        <h4 className="font-medium mb-3">Return to Automation</h4>
                        <div className="space-y-3">
                            <div className="space-y-2">
                                <Label>Reason for Return</Label>
                                <select
                                    value={returnReason}
                                    onChange={(e) => setReturnReason(e.target.value)}
                                    className="w-full h-10 rounded-md border border-input bg-background px-3 py-2 text-sm"
                                >
                                    <option value="">Select a reason...</option>
                                    <option value="poor_extraction">Poor document extraction quality</option>
                                    <option value="wrong_document">Wrong document type uploaded</option>
                                    <option value="missing_pages">Document has missing pages</option>
                                    <option value="illegible">Document is illegible</option>
                                    <option value="other">Other</option>
                                </select>
                            </div>
                            <div className="space-y-2">
                                <Label>Additional Comments</Label>
                                <Textarea
                                    value={returnComment}
                                    onChange={(e) => setReturnComment(e.target.value)}
                                    placeholder="Provide additional details..."
                                    className="min-h-[60px]"
                                />
                            </div>
                            <div className="flex gap-2">
                                <Button variant="outline" onClick={() => setShowReturnDialog(false)} className="flex-1">
                                    Cancel
                                </Button>
                                <Button
                                    onClick={handleReturnToAutomation}
                                    disabled={!returnReason}
                                    variant="destructive"
                                    className="flex-1"
                                >
                                    Confirm Return
                                </Button>
                            </div>
                        </div>
                    </div>
                </Card>
            )}

            {/* Action Buttons */}
            <div className="flex flex-col gap-3">
                {/* Primary Action */}
                <Button
                    onClick={handleApprove}
                    disabled={!canApprove}
                    className="w-full bg-success hover:bg-success/90 text-white h-12"
                    size="lg"
                >
                    <Lock className="mr-2" size={18} />
                    Approve & Lock Declaration
                    {!canApprove && (
                        <span className="ml-2 text-xs opacity-70">
                            ({issues.filter(i => i.type === 'missing').length} issues remaining)
                        </span>
                    )}
                </Button>

                {/* Secondary Actions */}
                <div className="grid grid-cols-2 gap-3">
                    <Button
                        variant="outline"
                        onClick={handleSaveDraft}
                        className="h-10"
                    >
                        <FloppyDisk className="mr-2" size={16} />
                        Save & Continue Later
                    </Button>
                    <Button
                        variant="outline"
                        onClick={() => setShowReturnDialog(true)}
                        className="h-10"
                    >
                        <ArrowCounterClockwise className="mr-2" size={16} />
                        Return to Automation
                    </Button>
                </div>
            </div>
        </div>
    )
}

export default ApprovalWorkflow
