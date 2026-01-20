/**
 * Document Preview Component
 * Displays document preview as a clean thumbnail using react-pdf
 */

import type { FC } from 'react'
import { Document, Thumbnail, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'

// Configure PDF.js worker from CDN
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`

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
        <div className="relative w-full h-full rounded-lg overflow-hidden bg-white flex items-center justify-center">
            {isPdf ? (
                <Document
                    file={fileUrl}
                    loading={
                        <div className="flex items-center justify-center h-full w-full">
                            <div className="text-muted-foreground text-sm">Loading...</div>
                        </div>
                    }
                    error={
                        <div className="flex items-center justify-center h-full w-full">
                            <div className="text-center p-4">
                                <div className="text-4xl mb-2">📄</div>
                                <p className="text-xs text-muted-foreground truncate max-w-[200px]">{fileName}</p>
                            </div>
                        </div>
                    }
                    className="flex items-center justify-center"
                >
                    <div className="border rounded-sm shadow-sm overflow-hidden">
                        <Thumbnail
                            pageNumber={1}
                            width={260}
                        />
                    </div>
                </Document>
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
