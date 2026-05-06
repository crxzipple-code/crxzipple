import { createRouter, createWebHistory } from "vue-router";

const OperationsShell = () => import("@/pages/operations/OperationsShell.vue");
const SettingsShell = () => import("@/pages/settings/SettingsShell.vue");
const TracePage = () => import("@/pages/trace/TracePage.vue");
const WorkbenchPage = () => import("@/pages/workbench/WorkbenchPage.vue");

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      redirect: "/workbench",
    },
    {
      path: "/workbench",
      name: "workbench",
      component: WorkbenchPage,
    },
    {
      path: "/workbench/threads/:sessionKey",
      name: "workbench-thread",
      component: WorkbenchPage,
    },
    {
      path: "/workbench/runs/:runId",
      name: "workbench-run",
      component: WorkbenchPage,
    },
    {
      path: "/operations/:module?",
      name: "operations",
      component: OperationsShell,
    },
    {
      path: "/trace/:traceId?",
      name: "trace",
      component: TracePage,
    },
    {
      path: "/settings/:resource?",
      name: "settings",
      component: SettingsShell,
    },
  ],
});
