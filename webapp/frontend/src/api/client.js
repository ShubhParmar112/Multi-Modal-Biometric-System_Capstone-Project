import axios from "axios";

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000",
  // Never let the UI wait forever on a stuck request.
  timeout: 30000,
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("smartbank_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// When the JWT expires (60 min), every call starts failing with 401.
// Clear the stale session and send the user back to the login page.
client.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    const isLoginCall = error.config?.url?.includes("/api/auth/login");
    if (status === 401 && !isLoginCall) {
      localStorage.removeItem("smartbank_token");
      localStorage.removeItem("smartbank_user");
      if (window.location.pathname !== "/login") {
        window.location.assign("/login");
      }
    }
    return Promise.reject(error);
  }
);

export default client;
