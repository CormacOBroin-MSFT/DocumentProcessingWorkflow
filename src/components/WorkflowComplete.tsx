/**
 * Workflow Complete Component
 * Success state after workflow completion
 */

import type { FC } from 'react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { CheckCircle } from '@phosphor-icons/react'

interface WorkflowCompleteProps {
    onReset: () => void
}

export const WorkflowComplete: FC<WorkflowCompleteProps> = ({ onReset }) => {
    return (
        <Card className="shadow-lg border-success/30">
            <div className="p-12 text-center">
                <CheckCircle size={64} className="mx-auto mb-4 text-success" weight="duotone" />
                <h2 className="text-2xl font-semibold mb-2 text-success">Workflow Complete!</h2>
                <p className="text-muted-foreground mb-6">
                    Document has been processed, approved, and submitted successfully.
                </p>
                <Button onClick={onReset} size="lg">
                    Process Another Document
                </Button>
            </div>
        </Card>
    )
}

export default WorkflowComplete
