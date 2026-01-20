/**
 * Document Preview Component
 * Displays document preview with optional scan animation
 */

import type { FC } from 'react'

interface DocumentPreviewProps {
    fileUrl: string
    fileName: string
    fileType?: string
    showScanAnimation?: boolean
}

export const DocumentPreview: FC<DocumentPreviewProps> = ({
    fileUrl,
    fileName,
    fileType,
    showScanAnimation = false,
}) => {
    const isPdf = fileType === 'application/pdf' || fileName.toLowerCase().endsWith('.pdf')

    return (
        <div className="relative aspect-video rounded-lg overflow-hidden bg-muted">
            {isPdf ? (
                <object data={fileUrl} type="application/pdf" className="w-full h-full">
                    <div className="flex items-center justify-center h-full bg-muted">
                        <div className="text-center p-4">
                            <div className="text-4xl mb-2">📄</div>
                            <p className="text-sm text-muted-foreground">{fileName}</p>
                            <a
                                href={fileUrl}
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
                <img src={fileUrl} alt={fileName} className="w-full h-full object-cover" />
            )}
            {showScanAnimation && (
                <div className="absolute inset-0 overflow-hidden">
                    <div className="absolute inset-x-0 h-0.5 bg-gradient-to-r from-transparent via-processing to-transparent scan-line" />
                </div>
            )}
        </div>
    )
}

export default DocumentPreview
