"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useI18n } from "@/components/I18n";
import { api } from "@/lib/api";

/** The API client, signed in as the current Clerk user. */
export function useApi() {
  const { getToken } = useAuth();
  return useMemo(() => api(() => getToken()), [getToken]);
}

/** Loads data once and on `reload()`, keeping the error to show. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(load, deps);
  const reload = useCallback(() => {
    setError(null);
    run().then(setData, (e: Error) => setError(e.message));
  }, [run]);
  useEffect(reload, [reload]);
  return { data, error, reload, setData };
}

/** Dates in the reader's language, e.g. "26 Eki 2026" in Turkish. */
export function useFormatDate() {
  const { locale } = useI18n();
  return useMemo(() => {
    const format = new Intl.DateTimeFormat(locale, { dateStyle: "medium" });
    return (iso: string) => format.format(new Date(iso));
  }, [locale]);
}
