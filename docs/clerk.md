# Setting up Clerk

1. Create an application at [dashboard.clerk.com](https://dashboard.clerk.com). Email sign-in is enough.
2. **API keys** page:
   - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY` go in `web/.env.local`.
   - The **Frontend API URL** (for example `https://your-app.clerk.accounts.dev`) goes in `backend/.env` as `CLERK_ISSUER`.
3. **Sessions → Customize session token**: add the email, so invites can check it:

   ```json
   {
     "email": "{{user.primary_email_address}}"
   }
   ```

   Without this claim, accepting an invite fails with a message pointing here. You can turn the check off with `INVITE_REQUIRES_EMAIL_MATCH=false`, but then anyone who gets the link can join.

4. In production, set `CORS_ORIGINS` on the API to your web app's URL. The API rejects session tokens issued to any other origin.

## Testing sign-in locally

Clerk development instances accept test addresses: any email with `+clerk_test` in it (for example `alice+clerk_test@example.com`) signs in with the code `424242`. Use two of them to try invites between users.
