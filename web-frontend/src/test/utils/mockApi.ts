/**
 * API mocking utilities using MSW
 */

import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { mockHosts, mockJobs, mockJobStatusResponse } from './mockData';
import type { JobInfo, HostInfo, JobStatusResponse } from '../../types/api';

// Match whatever baseURL the api service uses (empty string by default)
const baseURL = '';

/**
 * Default API handlers
 * Note: Using relative URLs to match the api service's empty baseURL
 */
export const handlers = [
  // GET /api/hosts
  http.get('/api/hosts', () => {
    return HttpResponse.json(mockHosts);
  }),

  // GET /api/status
  http.get('/api/status', ({ request }) => {
    const url = new URL(request.url);
    const host = url.searchParams.get('host');
    const forceRefresh = url.searchParams.get('force_refresh') === 'true';

    if (host) {
      const jobs = mockJobs.filter(j => j.hostname === host);
      const response: JobStatusResponse = {
        hostname: host,
        jobs,
        timestamp: new Date().toISOString(),
        query_time: forceRefresh ? '0.450s' : '0.123s',
        array_groups: [],
      };
      return HttpResponse.json(response);
    }

    // Return all jobs grouped by hostname
    const jobsByHost: Record<string, JobInfo[]> = {};
    mockJobs.forEach(job => {
      if (!jobsByHost[job.hostname]) {
        jobsByHost[job.hostname] = [];
      }
      jobsByHost[job.hostname].push(job);
    });

    return HttpResponse.json({
      jobs: jobsByHost,
      total: mockJobs.length,
    });
  }),

  // GET /api/jobs/:jobId
  http.get('/api/jobs/:jobId', ({ params, request }) => {
    const { jobId } = params;
    const url = new URL(request.url);
    const host = url.searchParams.get('host');

    const job = mockJobs.find(j =>
      j.job_id === jobId && (!host || j.hostname === host)
    );

    if (job) {
      return HttpResponse.json(job);
    }

    return HttpResponse.json(
      { detail: 'Job not found' },
      { status: 404 }
    );
  }),

  // GET /api/jobs/:jobId/output
  http.get('/api/jobs/:jobId/output', ({ params, request }) => {
    const { jobId } = params;
    const url = new URL(request.url);
    const outputType = url.searchParams.get('output_type') || 'stdout';

    return HttpResponse.json({
      job_id: jobId,
      output_type: outputType,
      content: `Mock ${outputType} content for job ${jobId}`,
      size: 100,
    });
  }),
];

/**
 * Create and setup MSW server
 */
export const server = setupServer(...handlers);

/**
 * Helper to add custom handlers
 */
export function addHandler(handler: any) {
  server.use(handler);
}

/**
 * Helper to create error response
 */
export function createErrorHandler(endpoint: string, status: number, message: string) {
  return http.get(endpoint, () => {
    return HttpResponse.json({ detail: message }, { status });
  });
}

/**
 * Helper to create timeout handler
 */
export function createTimeoutHandler(endpoint: string, delay: number = 31000) {
  return http.get(endpoint, async () => {
    await new Promise(resolve => setTimeout(resolve, delay));
    return HttpResponse.json({ detail: 'Timeout' }, { status: 504 });
  });
}

/**
 * Setup MSW for tests
 */
export function setupMSW() {
  beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
  afterEach(() => server.resetHandlers());
  afterAll(() => server.close());
}
