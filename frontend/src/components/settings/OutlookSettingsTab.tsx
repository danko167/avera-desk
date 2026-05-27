import {
  ActionIcon,
  Anchor,
  Button,
  Group,
  Loader,
  HoverCard,
  ScrollArea,
  Select,
  Slider,
  Stack,
  Text,
  TextInput,
  Tooltip,
  Divider,
} from "@mantine/core";
import { IconQuestionMark } from "@tabler/icons-react";
import { useEffect, useMemo, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import {
  fetchEmailSyncStatus,
  syncEmailsNow,
  type AppSettings,
  type OAuthStatus,
} from "../../lib/api";
import { createLogger } from "../../lib/logger";
import {
  validateClientId,
  validateGmailClientSecret,
  validateRedirectUrl,
  validateTenantId,
} from "../../lib/settingsValidation";

const logger = createLogger("OutlookSettingsTab");

type OutlookSettingsTabProps = {
  settings: AppSettings;
  gmailClientSecretInput: string;
  oauthStatus: OAuthStatus;
  isLoading: boolean;
  isSaving: boolean;
  onChange: (next: AppSettings) => void;
  onGmailClientSecretChange: (value: string) => void;
  onSyncIntervalCommit: (minutes: number) => void;
  onConnect: () => void;
  onDisconnect: () => void;
  onSave: () => void;
};

export function OutlookSettingsTab({
  settings,
  gmailClientSecretInput,
  oauthStatus,
  isLoading,
  isSaving,
  onChange,
  onGmailClientSecretChange,
  onSyncIntervalCommit,
  onConnect,
  onDisconnect,
  onSave,
}: OutlookSettingsTabProps) {
  const [secondsUntilNextSync, setSecondsUntilNextSync] = useState<number | null>(
    null
  );
  const [isManualSyncing, setIsManualSyncing] = useState(false);
  const [syncStatusText, setSyncStatusText] = useState("");

  const formattedCountdown = useMemo(() => {
    if (secondsUntilNextSync === null) {
      return "--:--";
    }

    const minutes = Math.floor(secondsUntilNextSync / 60);
    const seconds = secondsUntilNextSync % 60;
    return `${minutes}:${String(seconds).padStart(2, "0")}`;
  }, [secondsUntilNextSync]);

  useEffect(() => {
    let cancelled = false;

    const loadSyncStatus = async () => {
      try {
        const status = await fetchEmailSyncStatus();
        if (!cancelled) {
          setSecondsUntilNextSync(status.seconds_until_next_sync);
        }
      } catch {
        if (!cancelled) {
          setSecondsUntilNextSync(null);
        }
      }
    };

    void loadSyncStatus();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setSecondsUntilNextSync((prev) => {
        if (prev === null) return null;
        if (prev > 0) {
          return prev - 1;
        }
        return Math.max(1, settings.email_sync_interval_minutes) * 60;
      });
    }, 1000);

    return () => {
      window.clearInterval(timer);
    };
  }, [settings.email_sync_interval_minutes]);

  const handleManualSync = async () => {
    setIsManualSyncing(true);
    setSyncStatusText("");

    try {
      const result = await syncEmailsNow();
      const newUnreadCount = result.new_emails?.length ?? 0;

      if (result.status === "not authenticated") {
        setSyncStatusText("Connect your mailbox first to run manual sync.");
      } else {
        setSyncStatusText(
          `Manual sync done: ${result.count} item(s) checked, ${newUnreadCount} new unread.`
        );

        try {
          const status = await fetchEmailSyncStatus();
          setSecondsUntilNextSync(status.seconds_until_next_sync);
        } catch {
          setSecondsUntilNextSync(null);
        }
      }
    } catch (error) {
      logger.error("Manual sync failed.", error);
      setSyncStatusText("Manual sync failed. Please try again.");
    } finally {
      setIsManualSyncing(false);
    }
  };

  const handleSyncIntervalChangeEnd = (value: number) => {
    onSyncIntervalCommit(value);
    setSyncStatusText("Sync interval saved. Scheduler countdown will update shortly.");
  };

  const configComplete = !!(
    settings.email_provider === "m365"
      ? settings.m365_client_id.trim() && settings.m365_tenant_id.trim()
      : settings.gmail_client_id.trim() && (gmailClientSecretInput.trim() || settings.gmail_client_secret_configured)
  );

  const oauthConnectionMessage = (() => {
    if (!oauthStatus.authenticated) {
      return {
        text: "Connect your mailbox to enable email insights and suggestions.",
        help: null,
      };
    }

    const mailboxLabel = oauthStatus.connected_mailbox ?? "your account";

    if (oauthStatus.persistence === "persistent") {
      return {
        text: `Connected as ${mailboxLabel}.`,
        help: "This connection is saved and should stay active after app restarts or PC reboots.",
      };
    }

    if (oauthStatus.persistence === "session") {
      return {
        text: `Connected as ${mailboxLabel}.`,
        help: "This connection is temporary. You may need to reconnect after closing the app or restarting your PC.",
      };
    }

    return {
      text: `Connected as ${mailboxLabel}.`,
      help: "Emails will sync automatically.",
    };
  })();

  return (
    <ScrollArea h="100%" offsetScrollbars>
      <Stack gap="xs" mb="md">
        <Stack gap={4}>
          <Group align="end" justify="space-between">
            <Select
              size="xs"
              label="Email provider"
              value={settings.email_provider}
              data={[
                { value: "m365", label: "Microsoft 365 (Outlook)" },
                { value: "gmail", label: "Gmail" },
              ]}
              onChange={(value) =>
                onChange({
                  ...settings,
                  email_provider: (value as "m365" | "gmail") ?? "m365",
                })
              }
              allowDeselect={false}
            />

            {oauthStatus.authenticated ? (
              <Button
                size="xs"
                variant="default"
                onClick={onDisconnect}
                disabled={isLoading}
              >
                {isLoading ? <Loader size="xs" /> : "Disconnect Mailbox"}
              </Button>
            ) : (
              <Button
                size="xs"
                onClick={onConnect}
                disabled={isLoading || !configComplete}
              >
                {isLoading ? <Loader size="xs" /> : "Connect Mailbox"}
              </Button>
            )}
          </Group>

          {settings.email_provider === "m365" &&
            !oauthStatus.authenticated &&
            !configComplete && (
              <Text size="xs" c="orange.6">
                Fill in Client ID and Tenant ID in the configuration below, then save before
                connecting.
              </Text>
            )}

          <Group gap={4} align="center">
            <Text size="xs" c="dimmed">
              {oauthConnectionMessage.text}
            </Text>

            {oauthConnectionMessage.help ? (
              <Tooltip label={oauthConnectionMessage.help} multiline w={260}>
                <ActionIcon size={12} radius="xl" variant="outline" color="gray">
                  <IconQuestionMark size={10} />
                </ActionIcon>
              </Tooltip>
            ) : null}
          </Group>
        </Stack>

        <Stack gap={4}>
          <Text size="xs" fw={500}>
            Inbox Sync Interval
          </Text>
          <Text size="xs" c="dimmed">
            Set how often the app checks for new emails. Shorter intervals mean more timely insights but can use more system resources.
          </Text>

          <Slider
            mt={4}
            px="lg"
            mb="lg"
            size="md"
            min={1}
            max={60}
            step={1}
            label={(value) => `${value} min`}
            marks={[
              { value: 1, label: "1m" },
              { value: 5, label: "5m" },
              { value: 15, label: "15m" },
              { value: 30, label: "30m" },
              { value: 60, label: "60m" },
            ]}
            styles={{
              markLabel: {
                fontSize: "12px",
              },
            }}
            value={settings.email_sync_interval_minutes}
            disabled={isSaving}
            onChange={(value) =>
              onChange({
                ...settings,
                email_sync_interval_minutes: value,
              })
            }
            onChangeEnd={handleSyncIntervalChangeEnd}
          />

          <Group gap="xs" align="center">
            <Button
              size="xs"
              variant="light"
              onClick={handleManualSync}
              disabled={!oauthStatus.authenticated || isManualSyncing || isSaving}
            >
              {isManualSyncing ? <Loader size="xs" /> : "Sync now"}
            </Button>

            <Text size="xs" c="dimmed">
              Next auto sync in {formattedCountdown}
            </Text>
          </Group>

          {syncStatusText ? (
            <Text size="xs" c="dimmed">
              {syncStatusText}
            </Text>
          ) : null}
        </Stack>

        <Divider mb={2} />

        <Stack gap={4}>
          <Group gap={4} align="center">
            <Text size="xs" fw={500}>
              Email Provider Configuration
            </Text>

            <HoverCard width={280} position="bottom-start" withArrow shadow="md" openDelay={150} closeDelay={250}>
              <HoverCard.Target>
                <ActionIcon size={12} radius="xl" variant="outline" color="gray">
                  <IconQuestionMark size={10} />
                </ActionIcon>
              </HoverCard.Target>

              <HoverCard.Dropdown p="xs">
                <Stack gap={6}>
                  <Text size="xs" fw={500}>
                    {settings.email_provider === "m365"
                      ? "Microsoft 365 setup"
                      : "Gmail setup"}
                  </Text>

                  <Text size="xs" c="dimmed">
                    {settings.email_provider === "m365"
                      ? "Create an OAuth app, then copy the Client ID, Tenant ID, and Redirect URL into the fields below."
                      : "Create OAuth credentials, then copy the Client ID, Client Secret, and Redirect URL into the fields below."}
                  </Text>

                  {settings.email_provider === "m365" ? (
                    <Text size="xs" c="dimmed">
                      Required delegated permissions: <em>Mail.Read</em>,{" "}
                      <em>Mail.Send</em>, <em>Calendars.Read</em>,{" "}
                      <em>People.Read</em>, and <em>User.Read</em>.
                    </Text>
                  ) : (
                    <Text size="xs" c="dimmed">
                      Use an OAuth client type that supports your app flow, then make sure the
                      Redirect URL matches the value below.
                    </Text>
                  )}

                  <Anchor
                    size="xs"
                    onClick={() =>
                      openUrl(
                        settings.email_provider === "m365"
                          ? "https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app"
                          : "https://developers.google.com/workspace/guides/create-credentials"
                      )
                    }
                    style={{ cursor: "pointer" }}
                  >
                    Open setup guide
                  </Anchor>
                </Stack>
              </HoverCard.Dropdown>
            </HoverCard>
          </Group>

          {settings.email_provider === "m365" ? (
            <>
              <TextInput
                size="xs"
                label="Client ID"
                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                description="The Application (client) ID shown on your app's Overview page."
                error={validateClientId(settings.m365_client_id)}
                value={settings.m365_client_id}
                onChange={(e) =>
                  onChange({
                    ...settings,
                    m365_client_id: e.currentTarget.value,
                  })
                }
              />

              <TextInput
                size="xs"
                label="Tenant ID"
                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                description='Tenant UUID, tenant domain, or one of: common, organizations, consumers.'
                error={validateTenantId(settings.m365_tenant_id)}
                value={settings.m365_tenant_id}
                onChange={(e) =>
                  onChange({
                    ...settings,
                    m365_tenant_id: e.currentTarget.value,
                  })
                }
              />

              <Text size="xs" c="dimmed">
                Alias behavior: common = work/school + personal, organizations = work/school only,
                consumers = personal only.
              </Text>

              <TextInput
                size="xs"
                label="Redirect URL"
                placeholder="http://localhost:8000/api/oauth/callback"
                description="Must match the Redirect URI configured in your OAuth app."
                error={validateRedirectUrl(settings.m365_redirect_url)}
                value={settings.m365_redirect_url}
                onChange={(e) =>
                  onChange({
                    ...settings,
                    m365_redirect_url: e.currentTarget.value,
                  })
                }
              />
            </>
          ) : (
            <>
              <TextInput
                size="xs"
                label="Gmail Client ID"
                placeholder="xxxxxxxxxx-abc.apps.googleusercontent.com"
                description="The OAuth client ID from Google Cloud."
                value={settings.gmail_client_id}
                onChange={(e) =>
                  onChange({
                    ...settings,
                    gmail_client_id: e.currentTarget.value,
                  })
                }
              />

              <TextInput
                type="password"
                size="xs"
                label="Gmail Client Secret"
                placeholder={settings.gmail_client_secret_configured ? "Stored in OS keychain" : "Enter client secret"}
                description={settings.gmail_client_secret_configured
                  ? "A client secret is already stored securely. Enter a new one only if you want to replace it."
                  : "The OAuth client secret from Google Cloud."}
                value={gmailClientSecretInput}
                error={validateGmailClientSecret(gmailClientSecretInput, {
                  required: settings.email_provider === "gmail" && !settings.gmail_client_secret_configured,
                })}
                onChange={(e) => onGmailClientSecretChange(e.currentTarget.value)}
              />

              <TextInput
                size="xs"
                label="Gmail Redirect URL"
                placeholder="http://localhost:8000/api/oauth/google/callback"
                description="Must match the Redirect URI configured in your OAuth client."
                error={validateRedirectUrl(settings.gmail_redirect_url)}
                value={settings.gmail_redirect_url}
                onChange={(e) =>
                  onChange({
                    ...settings,
                    gmail_redirect_url: e.currentTarget.value,
                  })
                }
              />
            </>
          )}

          <Button onClick={onSave} disabled={isSaving} size="xs" mt="sm">
            {isSaving ? <Loader size="xs" /> : "Save Configuration"}
          </Button>
        </Stack>
      </Stack>
    </ScrollArea>
  );
}