/**
 * Confidence Display Components
 * Shows confidence scores with visual progress bars
 */

import type { FC } from 'react'

interface ConfidenceDisplayProps {
    label: string
    score: number
}

export const getConfidenceColor = (confidence: number): string => {
    if (confidence >= 0.9) return 'text-success'
    if (confidence >= 0.8) return 'text-warning'
    return 'text-destructive'
}

export const getConfidenceLabel = (confidence: number): string => {
    if (confidence >= 0.9) return 'High'
    if (confidence >= 0.8) return 'Medium'
    return 'Low'
}

export const getConfidenceBgColor = (confidence: number): string => {
    if (confidence >= 0.9) return 'bg-success'
    if (confidence >= 0.8) return 'bg-warning'
    return 'bg-destructive'
}

export const ConfidenceDisplay: FC<ConfidenceDisplayProps> = ({ label, score }) => (
    <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <div className="flex items-center gap-2">
            <div className="w-24 h-1.5 bg-muted rounded-full overflow-hidden">
                <div
                    className={`h-full transition-all duration-500 ${getConfidenceBgColor(score)}`}
                    style={{ width: `${score * 100}%` }}
                />
            </div>
            <span
                className={`font-mono font-medium ${getConfidenceColor(score)} min-w-[3rem] text-right`}
            >
                {(score * 100).toFixed(0)}%
            </span>
        </div>
    </div>
)

export default ConfidenceDisplay
