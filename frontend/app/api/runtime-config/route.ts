import { NextResponse } from 'next/server';

export async function GET() {
  // Prefer a server-only env var; fall back to NEXT_PUBLIC if present
  const backendUrl = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || null;
  return NextResponse.json({ backendUrl });
}
