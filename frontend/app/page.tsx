"use client";

import { useEffect, useState } from "react";
import { io, type Socket } from "socket.io-client";

type LeaderboardEntry = {
  session: string;
  username: string;
  score: number;
};

type JoinResponse = {
  ok: boolean;
  score?: number;
  message?: string;
};

type ClickResponse = {
  ok: boolean;
  score?: number;
  message?: string;
};

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "/api/backend";

export default function Home() {
  const [username, setUsername] = useState("");
  const [session, setSession] = useState<string | null>(null);
  const [score, setScore] = useState(0);
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
  const [status, setStatus] = useState("Disconnected");
  const [message, setMessage] = useState("Choose a name and start clicking.");
  const [socket, setSocket] = useState<Socket | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const savedUsername = window.localStorage.getItem("clicker_username");
    const savedSession = window.localStorage.getItem("clicker_session");

    if (savedUsername) {
      setUsername(savedUsername);
    }

    if (savedSession) {
      setSession(savedSession);
    }
  }, []);

  useEffect(() => {
    if (!session) {
      return;
    }

    const client = io(backendUrl, {
      transports: ["websocket"],
    });

    setSocket(client);
    setStatus("Connecting");

    client.on("connect", () => {
      setStatus("Connected");
      client.emit("join", { session }, (response: JoinResponse) => {
        if (!response?.ok) {
          setMessage(response?.message ?? "Could not join the game.");
          setStatus("Disconnected");
          return;
        }

        if (typeof response.score === "number") {
          setScore(response.score);
        }
      });
    });

    client.on("score_state", (payload: { score: number; leaderboard: LeaderboardEntry[] }) => {
      setScore(payload.score);
      setLeaderboard(payload.leaderboard);
    });

    client.on("score_update", (payload: { score: number }) => {
      setScore(payload.score);
    });

    client.on("leaderboard_update", (payload: { leaderboard: LeaderboardEntry[] }) => {
      setLeaderboard(payload.leaderboard);
    });

    client.on("disconnect", () => {
      setStatus("Disconnected");
    });

    client.on("connect_error", () => {
      setStatus("Connection failed");
    });

    return () => {
      client.disconnect();
      setSocket(null);
    };
  }, [session]);

  useEffect(() => {
    if (!session) {
      return;
    }

    void fetch(`${backendUrl}/api/flask/get_score?session=${encodeURIComponent(session)}`)
      .then(async (response) => {
        if (!response.ok) {
          return null;
        }

        return (await response.json()) as { score: number };
      })
      .then((data) => {
        if (data) {
          setScore(data.score);
        }
      });

  }, [session]);

  useEffect(() => {
    void fetch(`${backendUrl}/api/flask/get_leaderboard`)
      .then(async (response) => {
        if (!response.ok) {
          return null;
        }

        return (await response.json()) as LeaderboardEntry[];
      })
      .then((data) => {
        if (Array.isArray(data)) {
          setLeaderboard(data);
        }
      });
  }, []);

  async function handleCreateUser(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedUsername = username.trim();
    if (!trimmedUsername) {
      setMessage("Enter a username first.");
      return;
    }

    setMessage("Creating your player...");

    const response = await fetch(`${backendUrl}/api/flask/create_user`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ username: trimmedUsername }),
    });

    const data = (await response.json()) as {
      message?: string;
      session?: string;
      username?: string;
      score?: number;
    };

    if (!response.ok || !data.session) {
      setMessage(data.message ?? "Could not create the player.");
      return;
    }

    if (typeof window !== "undefined") {
      window.localStorage.setItem("clicker_username", trimmedUsername);
      window.localStorage.setItem("clicker_session", data.session);
    }

    setSession(data.session);
    setScore(data.score ?? 0);
    setMessage(`Ready as ${data.username ?? trimmedUsername}. Click the button.`);
  }

  function handleClick() {
    if (!socket || !session) {
      setMessage("Connect a player before clicking.");
      return;
    }

    socket.emit("click", { session }, (response: ClickResponse) => {
      if (!response?.ok) {
        setMessage(response?.message ?? "Click rejected.");
        return;
      }

      if (typeof response.score === "number") {
        setScore(response.score);
      }
    });
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,_#1e293b,_#020617_65%)] px-6 py-10 text-white sm:px-10 lg:px-16">
      <div className="mx-auto grid min-h-[calc(100vh-5rem)] max-w-6xl gap-8 lg:grid-cols-[1.5fr_0.9fr]">
        <section className="flex flex-col justify-between rounded-[2rem] border border-white/10 bg-white/8 p-8 shadow-2xl shadow-black/40 backdrop-blur-xl sm:p-10">
          <div className="space-y-6">
            <div className="inline-flex rounded-full border border-emerald-400/30 bg-emerald-400/10 px-4 py-1 text-sm font-medium text-emerald-200">
              {status}
            </div>
            <div className="space-y-3">
              <p className="text-sm uppercase tracking-[0.3em] text-sky-200/70">Simple Clicker</p>
              <h1 className="max-w-xl text-4xl font-semibold tracking-tight text-white sm:text-6xl">
                A tiny realtime game with server-validated clicks.
              </h1>
              <p className="max-w-2xl text-base leading-7 text-slate-200/80 sm:text-lg">
                The browser sends click events, Flask checks the session, updates Postgres, and Socket.IO pushes the new score back immediately.
              </p>
            </div>
          </div>

          <div className="grid gap-4 pt-8 sm:grid-cols-[1.2fr_0.8fr]">
            {!session ? (
            <form onSubmit={handleCreateUser} className="rounded-3xl border border-white/10 bg-slate-950/40 p-4">
              <label className="mb-2 block text-sm font-medium text-slate-200" htmlFor="userName">Player name</label>
              <div className="flex flex-col gap-3 sm:flex-row">
                <input
                  id="userName"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  placeholder="Enter a name"
                  className="h-12 flex-1 rounded-2xl border border-white/10 bg-slate-900/80 px-4 text-white outline-none transition placeholder:text-slate-400 focus:border-sky-400/60"
                />
                <button
                  type="submit"
                  className="h-12 rounded-2xl bg-sky-400 px-5 font-semibold text-slate-950 transition hover:bg-sky-300"
                >
                  Start
                </button>
              </div>
            
            </form>) : (
               <div className="rounded-3xl border border-white/10 bg-slate-950/40 p-4">
              <p className="mb-2 block text-sm font-medium text-slate-200">Player name</p>
              <div className="flex flex-col gap-3">
                <p
                  className="h-12  rounded-2xl border border-white/10 bg-slate-900/80 px-4 py-3 text-xl text-white outline-none transition placeholder:text-slate-400 focus:border-sky-400/60 text-center"
                >
                  {username}
                </p>
              </div>
               <button
                  onClick={() => {
                    if (typeof window !== "undefined") {
                      window.localStorage.removeItem("clicker_username");
                      window.localStorage.removeItem("clicker_session");
                    }
                    setUsername("");
                    setSession(null);
                    setScore(0);
                    setMessage("Choose a name and start clicking.");
                  }}
                  type="button"
                  className="h-9 rounded-2xl bg-red-400 px-5 font-semibold text-slate-950 transition hover:bg-red-300 justify-center items-center mt-2 w-full flex"
                >
                  Disconnect
                </button>
            </div>
            )}

            <div className="rounded-3xl border border-white/10 bg-slate-950/40 p-4">
              <p className="text-sm font-medium text-slate-300">Connection</p>
              <p className="mt-2 text-2xl font-semibold text-white">{status}</p>
              <p className="mt-2 text-sm leading-6 text-slate-300">{message}</p>
            </div>
          </div>
        </section>

        <aside className="flex flex-col gap-6 rounded-[2rem] border border-white/10 bg-slate-950/50 p-6 shadow-2xl shadow-black/30 backdrop-blur-xl sm:p-8">
          <div className="rounded-[1.75rem] border border-sky-400/20 bg-sky-400/10 p-6 text-center">
            <p className="text-sm uppercase tracking-[0.3em] text-sky-200/70">Score</p>
            <div className="mt-3 text-6xl font-black text-white">{score}</div>
            <button
              type="button"
              onClick={handleClick}
              className="mt-6 h-14 w-full rounded-2xl bg-emerald-400 text-lg font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-300"
              disabled={!session}
            >
              Click me
            </button>
          </div>

          <div className="flex-1 rounded-[1.75rem] border border-white/10 bg-white/5 p-5">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-white">Leaderboard</h2>
              <span className="text-sm text-slate-400">Top 10</span>
            </div>
            <div className="mt-4 space-y-3">
              {leaderboard.length === 0 ? (
                <p className="text-sm text-slate-400">No scores yet. Be first.</p>
              ) : (
                leaderboard.map((entry, index) => (
                  <div
                    key={`${entry.session}-${entry.username}`}
                    className="flex items-center justify-between rounded-2xl border border-white/8 bg-slate-900/60 px-4 py-3"
                  >
                    <div>
                      <p className="text-sm text-slate-400">#{index + 1}</p>
                      <p className="font-medium text-white">{entry.username}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Score</p>
                      <p className="text-xl font-semibold text-emerald-300">{entry.score}</p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </aside>
      </div>
    </main>
  );
}
