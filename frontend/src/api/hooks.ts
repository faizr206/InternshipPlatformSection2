import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./endpoints";
import type { HomeQuery, Scenario } from "./types";

export const qk = {
  students: ["students"] as const,
  demo: ["demo-settings"] as const,
  journey: (id: string) => ["journey", id] as const,
  todos: (q: HomeQuery) => ["todos", q.role, q.student_id] as const,
  counts: (q: HomeQuery) => ["nav-counts", q.role, q.student_id] as const,
  events: (studentId?: string) => ["events", studentId ?? "all"] as const,
};

export const useStudents = () => useQuery({ queryKey: qk.students, queryFn: api.students, staleTime: Infinity });
export const useDemoSettings = () => useQuery({ queryKey: qk.demo, queryFn: api.demoSettings });
export const useJourney = (studentId: string) =>
  useQuery({ queryKey: qk.journey(studentId), queryFn: () => api.journey(studentId), placeholderData: keepPreviousData });
export const useTodos = (q: HomeQuery) => useQuery({ queryKey: qk.todos(q), queryFn: () => api.todos(q), placeholderData: keepPreviousData });
export const useNavCounts = (q: HomeQuery) =>
  useQuery({ queryKey: qk.counts(q), queryFn: () => api.navCounts(q), placeholderData: keepPreviousData });
export const useEvents = (studentId?: string) =>
  useQuery({
    queryKey: qk.events(studentId),
    queryFn: () => api.events({ limit: 12, student_id: studentId }),
  });

/** Changing the demo clock or scenario changes everything, so refetch all. */
export function useResetScenario() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (s: Scenario) => api.resetScenario(s),
    onSuccess: () => qc.invalidateQueries(),
  });
}

export function useSetToday() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (d: string) => api.setToday(d),
    onSuccess: () => qc.invalidateQueries(),
  });
}

export const useAskAssistant = () =>
  useMutation({
    mutationFn: (v: { question: string; role: string; student_id?: string }) => api.askAssistant(v.question, v.role, v.student_id),
  });
