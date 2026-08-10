import { z } from "zod";

/**
 * Password policy — must mirror the backend exactly
 * (`backend/app/schemas/auth.py::validate_password_strength`): at least 8
 * chars with a lowercase letter, an uppercase letter, and a digit. Kept
 * client-side so users get inline feedback instead of a generic 422.
 */
export const passwordSchema = z
  .string()
  .min(8, "Password must be at least 8 characters")
  .regex(/[a-z]/, "Password must contain a lowercase letter")
  .regex(/[A-Z]/, "Password must contain an uppercase letter")
  .regex(/[0-9]/, "Password must contain a digit");
