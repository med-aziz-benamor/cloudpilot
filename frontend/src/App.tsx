import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AnimatePresence } from "framer-motion";
import { useEffect } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { AppShell } from "@/components/layout/AppShell";
import { Toaster } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useAuth } from "@/hooks/useAuth";
import { LoginPage } from "@/pages/auth/LoginPage";
import { ChatPage } from "@/pages/chat/ChatPage";
import { CostsPage } from "@/pages/costs/CostsPage";
import { ForecastPage } from "@/pages/forecast/ForecastPage";
import { OverviewPage } from "@/pages/overview/OverviewPage";
import { RecommendationsPage } from "@/pages/recommendations/RecommendationsPage";
import { ResourcesPage } from "@/pages/resources/ResourcesPage";
import { ConnectCloudPage } from "@/pages/settings/ConnectCloudPage";
import { SettingsPage } from "@/pages/settings/SettingsPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function AnimatedRoutes() {
  const location = useLocation();
  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          }
        >
          <Route path="/" element={<OverviewPage />} />
          <Route path="/resources" element={<ResourcesPage />} />
          <Route path="/costs" element={<CostsPage />} />
          <Route path="/recommendations" element={<RecommendationsPage />} />
          <Route path="/forecast" element={<ForecastPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/settings/connect" element={<ConnectCloudPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AnimatePresence>
  );
}

function SessionBootstrap({ children }: { children: React.ReactNode }) {
  const { loadSession } = useAuth();
  useEffect(() => {
    void loadSession();
  }, [loadSession]);
  return <>{children}</>;
}

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider delayDuration={200}>
          <BrowserRouter>
            <SessionBootstrap>
              <AnimatedRoutes />
            </SessionBootstrap>
            <Toaster />
          </BrowserRouter>
        </TooltipProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
