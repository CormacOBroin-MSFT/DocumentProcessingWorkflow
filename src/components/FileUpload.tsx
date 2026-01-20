/**
 * File Upload Component
 * Drag and drop file upload with visual feedback
 */

import { useState, useCallback, type FC } from 'react'
import { Card } from '@/components/ui/card'
import { CloudArrowUp } from '@phosphor-icons/react'

interface FileUploadProps {
    onFileSelect: (file: File) => void
    accept?: string
    title?: string
    description?: string
    inputId?: string
}

export const FileUpload: FC<FileUploadProps> = ({
    onFileSelect,
    accept = 'image/*,application/pdf',
    title = 'Upload Document',
    description = 'Upload a document to begin processing',
    inputId = 'file-input',
}) => {
    const [isDragging, setIsDragging] = useState(false)

    const handleDrop = useCallback(
        (e: React.DragEvent) => {
            e.preventDefault()
            setIsDragging(false)
            const file = e.dataTransfer.files[0]
            if (file) {
                // Validate file type
                const acceptTypes = accept.split(',').map((t) => t.trim())
                const isValid = acceptTypes.some((type) => {
                    if (type.includes('*')) {
                        const [category] = type.split('/')
                        return file.type.startsWith(category + '/')
                    }
                    return file.type === type
                })

                if (isValid) {
                    onFileSelect(file)
                }
            }
        },
        [accept, onFileSelect]
    )

    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault()
        setIsDragging(true)
    }, [])

    const handleDragLeave = useCallback(() => {
        setIsDragging(false)
    }, [])

    const handleFileChange = useCallback(
        (e: React.ChangeEvent<HTMLInputElement>) => {
            const file = e.target.files?.[0]
            if (file) {
                onFileSelect(file)
            }
        },
        [onFileSelect]
    )

    const handleClick = useCallback(() => {
        document.getElementById(inputId)?.click()
    }, [inputId])

    return (
        <Card className="shadow-lg">
            <div className="p-8">
                <div className="text-center mb-6">
                    <CloudArrowUp size={48} className="mx-auto mb-4 text-accent" weight="duotone" />
                    <h2 className="text-2xl font-semibold mb-2">{title}</h2>
                    <p className="text-muted-foreground">{description}</p>
                </div>
                <div
                    onDrop={handleDrop}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-all ${isDragging
                            ? 'border-accent bg-accent/10 scale-[1.02]'
                            : 'border-border hover:border-accent/50 hover:bg-accent/5'
                        }`}
                    onClick={handleClick}
                >
                    <CloudArrowUp size={64} className="mx-auto mb-4 text-muted-foreground" />
                    <p className="text-lg font-medium mb-2">Drop your document here</p>
                    <p className="text-sm text-muted-foreground">or click to browse (PDF, PNG, JPG)</p>
                    <input
                        id={inputId}
                        type="file"
                        accept={accept}
                        onChange={handleFileChange}
                        className="hidden"
                    />
                </div>
            </div>
        </Card>
    )
}

export default FileUpload
