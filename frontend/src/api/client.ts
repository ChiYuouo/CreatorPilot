import axios from "axios";
import { useAuthStore } from "../stores/auth";

const client = axios.create({ baseURL: "/api/v1" });

// 请求拦截：自动附带访问令牌
client.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 响应拦截：401 时用刷新令牌换新并重试一次，失败则登出
client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original._retried) {
      original._retried = true;
      const refreshToken = useAuthStore.getState().refreshToken;
      if (!refreshToken) {
        useAuthStore.getState().clear();
        return Promise.reject(error);
      }
      try {
        // 注意：这里必须用裸 axios，避免走本拦截器造成循环
        const { data } = await axios.post("/api/v1/auth/refresh", {
          refresh_token: refreshToken,
        });
        useAuthStore
          .getState()
          .setAuth(data.access_token, data.refresh_token, data.user);
        original.headers.Authorization = `Bearer ${data.access_token}`;
        return client(original);
      } catch {
        useAuthStore.getState().clear();
        return Promise.reject(error);
      }
    }
    return Promise.reject(error);
  }
);

export default client;
