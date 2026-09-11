import { useCallback, useEffect, useState } from 'react';

import { apiClient } from '@/services/api';
import type { DiskUsage, JobSummary } from '@/types';

const PAGE_SIZE = 25;

/**
 * Backs the Operations section: recent processing jobs (paginated, filterable
 * by status) and the data-volume disk-usage breakdown.
 */
export function useJobs() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState('');
  const [diskUsage, setDiskUsage] = useState<DiskUsage | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    try {
      const [jobList, disk] = await Promise.all([
        apiClient.getJobs({ status: status || undefined, limit: PAGE_SIZE, offset }),
        apiClient.getDiskUsage(),
      ]);
      setJobs(jobList.jobs);
      setTotal(jobList.total);
      setDiskUsage(disk);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load job history');
    } finally {
      setIsLoading(false);
    }
  }, [status, offset]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const changeStatus = useCallback((value: string) => {
    setStatus(value);
    setOffset(0); // a new filter starts back at the first page
  }, []);

  return {
    jobs,
    total,
    offset,
    setOffset,
    status,
    setStatus: changeStatus,
    pageSize: PAGE_SIZE,
    diskUsage,
    refresh,
    isLoading,
    error,
  };
}
