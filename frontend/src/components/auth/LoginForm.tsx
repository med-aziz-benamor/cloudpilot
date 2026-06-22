import { motion, useAnimationControls } from "framer-motion";
import { Eye, EyeOff, Loader2, Lock, Mail } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiErrorMessage } from "@/lib/api";
import { DEMO_CREDENTIALS } from "@/lib/constants";
import { useAuthStore } from "@/stores/auth.store";

export function LoginForm() {
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();
  const controls = useAnimationControls();

  const [email, setEmail] = useState(DEMO_CREDENTIALS.email);
  const [password, setPassword] = useState(DEMO_CREDENTIALS.password);
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login({ email, password });
      navigate("/");
    } catch (err) {
      setError(apiErrorMessage(err));
      await controls.start({
        x: [0, -10, 10, -8, 8, 0],
        transition: { duration: 0.4 },
      });
    } finally {
      setLoading(false);
    }
  };

  const tryDemo = async () => {
    setEmail(DEMO_CREDENTIALS.email);
    setPassword(DEMO_CREDENTIALS.password);
    setLoading(true);
    setError(null);
    try {
      await login(DEMO_CREDENTIALS);
      navigate("/");
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.form
      onSubmit={submit}
      animate={controls}
      className="w-full max-w-sm"
    >
      <h1 className="text-h1 font-bold text-neutral-900">Welcome back</h1>
      <p className="mt-1 text-body text-neutral-500">
        Sign in to your CloudPilot cockpit.
      </p>

      <div className="mt-8 space-y-4">
        <div>
          <label className="mb-1.5 block text-body-sm font-medium text-neutral-700">
            Email
          </label>
          <div className="relative">
            <Mail
              size={16}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400"
            />
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              className="pl-9"
              placeholder="you@company.com"
            />
          </div>
        </div>

        <div>
          <label className="mb-1.5 block text-body-sm font-medium text-neutral-700">
            Password
          </label>
          <div className="relative">
            <Lock
              size={16}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400"
            />
            <Input
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              className="px-9"
              placeholder="••••••••"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600"
              aria-label={showPassword ? "Hide password" : "Show password"}
            >
              {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
        </div>

        {error && (
          <p className="rounded-md bg-status-danger/10 px-3 py-2 text-body-sm text-status-danger">
            {error}
          </p>
        )}

        <Button type="submit" size="lg" className="w-full" disabled={loading}>
          {loading ? <Loader2 size={18} className="animate-spin" /> : "Sign in"}
        </Button>

        <button
          type="button"
          onClick={tryDemo}
          disabled={loading}
          className="w-full text-center text-body-sm font-medium text-brand-primary hover:underline"
        >
          Try Demo →
        </button>
      </div>

      <p className="mt-8 text-center text-caption text-neutral-400">
        🔒 Secured by CloudPilot Security v1.0
      </p>
    </motion.form>
  );
}
