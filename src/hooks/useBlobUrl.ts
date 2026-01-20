/**
 * Custom hook for managing blob URLs with proper cleanup
 * Prevents memory leaks from unreleased Object URLs
 */

import { useState, useCallback, useEffect, useRef } from 'react'

interface UseBlobUrlReturn {
    /** Current blob URL (null if no file) */
    blobUrl: string | null
    /** Create a blob URL from a file */
    createUrl: (file: File) => string
    /** Manually clear the current URL */
    clearUrl: () => void
}

/**
 * Hook to manage blob URLs with automatic cleanup on unmount
 * 
 * @example
 * ```tsx
 * const { blobUrl, createUrl, clearUrl } = useBlobUrl()
 * 
 * const handleFileUpload = (file: File) => {
 *   const url = createUrl(file)
 *   // url is now available for <img>, <iframe>, etc.
 * }
 * ```
 */
export function useBlobUrl(): UseBlobUrlReturn {
    const [blobUrl, setBlobUrl] = useState<string | null>(null)
    const urlRef = useRef<string | null>(null)

    // Cleanup function
    const revokeUrl = useCallback(() => {
        if (urlRef.current) {
            URL.revokeObjectURL(urlRef.current)
            urlRef.current = null
        }
    }, [])

    // Create a new blob URL (revoking any previous one)
    const createUrl = useCallback((file: File): string => {
        // Revoke previous URL to prevent memory leak
        revokeUrl()

        const url = URL.createObjectURL(file)
        urlRef.current = url
        setBlobUrl(url)
        return url
    }, [revokeUrl])

    // Manually clear the URL
    const clearUrl = useCallback(() => {
        revokeUrl()
        setBlobUrl(null)
    }, [revokeUrl])

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            revokeUrl()
        }
    }, [revokeUrl])

    return { blobUrl, createUrl, clearUrl }
}

/**
 * Hook to manage multiple blob URLs (e.g., for file list previews)
 */
export function useBlobUrls(): {
    urls: Map<string, string>
    createUrl: (id: string, file: File) => string
    removeUrl: (id: string) => void
    clearAll: () => void
} {
    const urlsRef = useRef<Map<string, string>>(new Map())
    const [, forceUpdate] = useState({})

    const createUrl = useCallback((id: string, file: File): string => {
        // Revoke existing URL for this ID
        const existing = urlsRef.current.get(id)
        if (existing) {
            URL.revokeObjectURL(existing)
        }

        const url = URL.createObjectURL(file)
        urlsRef.current.set(id, url)
        forceUpdate({})
        return url
    }, [])

    const removeUrl = useCallback((id: string) => {
        const url = urlsRef.current.get(id)
        if (url) {
            URL.revokeObjectURL(url)
            urlsRef.current.delete(id)
            forceUpdate({})
        }
    }, [])

    const clearAll = useCallback(() => {
        urlsRef.current.forEach((url) => URL.revokeObjectURL(url))
        urlsRef.current.clear()
        forceUpdate({})
    }, [])

    // Cleanup all URLs on unmount
    useEffect(() => {
        return () => {
            urlsRef.current.forEach((url) => URL.revokeObjectURL(url))
        }
    }, [])

    return {
        urls: urlsRef.current,
        createUrl,
        removeUrl,
        clearAll,
    }
}
