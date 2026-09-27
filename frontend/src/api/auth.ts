import client from "./client";
import type { User } from "../stores/auth";

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

export const authApi = {
  register: (data: { email: string; password: string; nickname: string }) =>
    client.post<User>("/auth/register", data),
  login: (data: { email: string; password: string }) =>
    client.post<TokenResponse>("/auth/login", data),
  me: () => client.get<User>("/users/me"),
};
