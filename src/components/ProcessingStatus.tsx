/**
 * Processing Status Component
 * Shows processing steps with status indicators
 */

import type { FC } from 'react'
import { Card } from '@/components/ui/card'
import { CheckCircle, Clock, X, ScanSmiley, Warning } from '@phosphor-icons/react'
import { DocumentPreview } from './DocumentPreview'
import type { ProcessingStep } from '@/types/customs'

interface ProcessingStatusProps {
    status: string
    steps: ProcessingStep[]
    document?: {
        fileUrl: string
        fileName: string
        fileType?: string
    } | null
}

export const ProcessingStatus: FC<ProcessingStatusProps> = ({
    status,
    steps,
    document,
}) => {
    return (
        <Card className="shadow-lg">
            <div className="p-8">
                <div className="text-center mb-8">
                    <div className="inline-block animate-spin mb-4">
                        <ScanSmiley size={48} className="text-processing" weight="duotone" />
                    </div>
                    <h2 className="text-2xl font-semibold mb-2">Processing Document</h2>
                    <p className="text-muted-foreground">{status}</p>
                </div>

                {/* Document Preview */}
                {document && (
                    <div className="mb-8 flex justify-center">
                        <div className="w-80 h-96 rounded-lg overflow-hidden bg-transparent">
                            <DocumentPreview
                                fileUrl={document.fileUrl}
                                fileName={document.fileName}
                                fileType={document.fileType}
                            />
                        </div>
                    </div>
                )}

                {/* Processing Steps */}
                <div className="space-y-4 max-w-md mx-auto">
                    {steps.map((step, index) => (
                        <div key={step.id} className="flex items-center gap-4">
                            <div
                                className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${step.status === 'complete'
                                    ? 'bg-success text-white'
                                    : step.status === 'in-progress'
                                        ? 'bg-processing text-white'
                                        : step.status === 'error'
                                            ? 'bg-destructive text-white'
                                            : step.status === 'warning'
                                                ? 'bg-amber-500 text-white'
                                                : 'bg-muted text-muted-foreground'
                                    }`}
                            >
                                {step.status === 'complete' ? (
                                    <CheckCircle size={18} weight="bold" />
                                ) : step.status === 'in-progress' ? (
                                    <Clock size={18} className="animate-spin" />
                                ) : step.status === 'error' ? (
                                    <X size={18} weight="bold" />
                                ) : step.status === 'warning' ? (
                                    <Warning size={18} weight="bold" />
                                ) : (
                                    <span className="text-xs font-medium">{index + 1}</span>
                                )}
                            </div>
                            <div className="flex flex-col">
                                <span
                                    className={`text-sm ${step.status === 'complete'
                                        ? 'text-success font-medium'
                                        : step.status === 'in-progress'
                                            ? 'text-processing font-medium'
                                            : step.status === 'error'
                                                ? 'text-destructive'
                                                : step.status === 'warning'
                                                    ? 'text-amber-600 font-medium'
                                                    : 'text-muted-foreground'
                                        }`}
                                >
                                    {step.label}
                                    {step.status === 'warning' && ' (partial)'}
                                </span>
                                {step.warningMessage && step.status === 'warning' && (
                                    <span className="text-xs text-amber-600 mt-0.5">
                                        {step.warningMessage}
                                    </span>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </Card>
    )
}

export default ProcessingStatus
