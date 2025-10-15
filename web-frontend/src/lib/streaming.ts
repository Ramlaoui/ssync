import pako from 'pako';
import { apiConfig } from '../services/api';
import { get } from 'svelte/store';

export class OutputStreamer {
    private eventSource: EventSource | null = null;
    private chunks: string[] = [];
    private compressedChunks: string[] = [];
    private metadata: any = null;
    private onChunk: (chunk: string) => void;
    private onComplete: () => void;
    private onError: (error: string) => void;
    
    constructor(
        onChunk: (chunk: string) => void,
        onComplete: () => void,
        onError: (error: string) => void
    ) {
        this.onChunk = onChunk;
        this.onComplete = onComplete;
        this.onError = onError;
    }
    
    async stream(url: string): Promise<void> {
        return new Promise((resolve, reject) => {
            // Add API key to URL if configured
            const config = get(apiConfig);
            if (config.apiKey) {
                const separator = url.includes('?') ? '&' : '?';
                url = `${url}${separator}api_key=${encodeURIComponent(config.apiKey)}`;
            }
            
            this.eventSource = new EventSource(url);
            
            this.eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    
                    if (data.type === 'metadata') {
                        // Store metadata for later use
                        this.metadata = data;
                        console.log('Stream metadata:', data);
                    } else if (data.type === 'chunk') {
                        // Handle compressed or uncompressed chunks
                        if (data.compressed) {
                            // Store compressed chunks - we'll decompress all at once at the end
                            this.compressedChunks[data.index] = data.data;
                        } else {
                            // Plain text chunk - display immediately
                            this.chunks[data.index] = data.data;
                            this.onChunk(data.data);
                        }
                    } else if (data.type === 'complete') {
                        // If we have compressed chunks, decompress them now
                        if (this.compressedChunks.length > 0) {
                            try {
                                // Combine all base64 chunks
                                const fullBase64 = this.compressedChunks.join('');
                                
                                // Decode base64 to binary
                                const binaryString = atob(fullBase64);
                                const bytes = new Uint8Array(binaryString.length);
                                for (let i = 0; i < binaryString.length; i++) {
                                    bytes[i] = binaryString.charCodeAt(i);
                                }
                                
                                // Decompress gzip
                                const decompressed = pako.ungzip(bytes, { to: 'string' });
                                
                                // Send decompressed content in smaller chunks to avoid memory issues
                                const CHUNK_SIZE = 50 * 1024; // 50KB chunks
                                for (let i = 0; i < decompressed.length; i += CHUNK_SIZE) {
                                    const chunk = decompressed.slice(i, i + CHUNK_SIZE);
                                    this.chunks.push(chunk);
                                    this.onChunk(chunk);
                                }
                            } catch (e) {
                                console.error('Decompression error:', e);
                                // Fall back to showing raw data
                                const fallback = '[Error: Failed to decompress output]';
                                this.chunks = [fallback];
                                this.onChunk(fallback);
                            }
                        }
                        
                        this.onComplete();
                        this.close();
                        resolve();
                    } else if (data.type === 'truncation_notice') {
                        // Add truncation notice to output
                        const notice = `\n[Output truncated - original size: ${data.original_size} bytes]\n`;
                        this.chunks.push(notice);
                        this.onChunk(notice);
                    } else if (data.type === 'error') {
                        this.onError(data.message || 'Unknown error');
                        this.close();
                        reject(new Error(data.message));
                    }
                } catch (e) {
                    console.error('Error parsing stream data:', e);
                    this.onError('Failed to parse stream data');
                    this.close();
                    reject(e);
                }
            };
            
            this.eventSource.onerror = (error) => {
                console.error('EventSource error:', error);
                this.onError('Connection lost');
                this.close();
                reject(error);
            };
        });
    }
    
    close(): void {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
    }
    
    getFullContent(): string {
        return this.chunks.join('');
    }
    
    getMetadata(): any {
        return this.metadata;
    }
}

// Helper function to stream output with proper URL construction
export async function streamJobOutput(
    jobId: string,
    hostname: string,
    outputType: 'stdout' | 'stderr',
    onChunk: (chunk: string) => void,
    onComplete: () => void,
    onError: (error: string) => void
): Promise<OutputStreamer> {
    // Build the streaming URL
    const baseUrl = import.meta.env.VITE_API_URL || '';
    const url = `${baseUrl}/api/jobs/${encodeURIComponent(jobId)}/output/stream?host=${encodeURIComponent(hostname)}&output_type=${outputType}`;
    
    const streamer = new OutputStreamer(onChunk, onComplete, onError);
    await streamer.stream(url);
    return streamer;
}