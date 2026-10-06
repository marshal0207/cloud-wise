import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  Cloud,
  Copy,
  ExternalLink,
  FileJson,
  Github,
  HelpCircle,
  Info,
  KeyRound,
  Loader2,
  Lock,
  RefreshCw,
  Rocket,
  Server,
  ShieldCheck,
  Terminal,
  Unplug,
  X,
} from 'lucide-react';
import { useCloudWise } from '@/context/CloudWiseContext';

interface AwsConnectionInfo {
  connected: boolean;
  status?: string;
  accountId?: string;
  roleArn?: string;
  externalId?: string;
  region?: string;
  connectedAt?: string | null;
}

interface ConnectInfo {
  externalId: string;
  trustedAccountId: string;
  trustPolicy: string;
  permissionsPolicy: string;
  instructions: string[];
  defaultRegion: string;
  platformCredentialsConfigured: boolean;
  connection: AwsConnectionInfo;
}

interface ConnectError {
  message: string;
  kind: string;
  technical?: string;
}

type VerifyStatus = 'pending' | 'running' | 'done' | 'failed';

interface VerifyStep {
  key: string;
  label: string;
  status: VerifyStatus;
  detail?: string;
}

type Phase = 'idle' | 'setup' | 'verifying';

const authHeaders = () => {
  const token = localStorage.getItem('cloudwise_token');
  return {
    'Content-Type': 'application/json',
    Authorization: token ? `Bearer ${token}` : '',
  };
};

const ARN_RE = /^arn:aws[a-zA-Z-]*:iam::\d{12}:role\/.+$/;

const AWS_CONSOLE_ROLE_URL = 'https://console.aws.amazon.com/iam/home#/roles/create';

const RECOMMENDED_ROLE_NAME = 'CloudWiseDeployRole';
const RECOMMENDED_POLICY_NAME = 'CloudWiseDeployPolicy';

const AWS_REGIONS: { code: string; name: string }[] = [
  { code: 'ap-south-1', name: 'Asia Pacific (Mumbai)' },
  { code: 'ap-southeast-1', name: 'Asia Pacific (Singapore)' },
  { code: 'ap-southeast-2', name: 'Asia Pacific (Sydney)' },
  { code: 'ap-northeast-1', name: 'Asia Pacific (Tokyo)' },
  { code: 'ca-central-1', name: 'Canada (Central)' },
  { code: 'eu-west-1', name: 'Europe (Ireland)' },
  { code: 'eu-west-2', name: 'Europe (London)' },
  { code: 'eu-central-1', name: 'Europe (Frankfurt)' },
  { code: 'eu-north-1', name: 'Europe (Stockholm)' },
  { code: 'sa-east-1', name: 'South America (Sao Paulo)' },
  { code: 'us-east-1', name: 'US East (N. Virginia)' },
  { code: 'us-east-2', name: 'US East (Ohio)' },
  { code: 'us-west-1', name: 'US West (N. California)' },
  { code: 'us-west-2', name: 'US West (Oregon)' },
];

const BASE_VERIFY_STEPS: VerifyStep[] = [
  { key: 'role', label: 'Checking role', status: 'pending' },
  { key: 'access', label: 'Verifying CloudWise access', status: 'pending' },
  { key: 'permissions', label: 'Checking deployment permissions', status: 'pending' },
  { key: 'region', label: 'Checking AWS region', status: 'pending' },
  { key: 'ready', label: 'Preparing connection', status: 'pending' },
];

const SETUP_STEPS = ['Account', 'Permission', 'Connect', 'Verify'];

const CLOUDWISE_HANDLES = [
  'Provision EC2',
  'Configure networking',
  'Prepare server',
  'Configure SSM',
  'Install/update Docker',
  'Prepare Buildx',
  'Upload application',
  'Build containers',
  'Start application',
  'Run health checks',
  'Return live URL',
];

const ERROR_HINTS: Record<string, string> = {
  trust: "The role's trust policy may not contain the CloudWise account ID or the correct External ID.",
  permissions: 'The role may be missing one or more deployment permissions.',
  region: 'The selected region may not be available to this role.',
  format: 'The value you pasted is not an IAM role ARN.',
  platform: 'The CloudWise server is missing its own platform credentials.',
};

const YOU_WILL = [
  'Create one CloudWise role in AWS',
  'Give that role the required deployment permissions',
  'Connect the role to CloudWise',
];

const YOU_WONT = [
  'Share your AWS password',
  'Share AWS access keys',
  'Configure an EC2 server',
  'Install Docker',
  'Run terminal commands',
];

const CLOUDWISE_CAN = [
  'Discover AWS resources',
  'Create or reuse deployment infrastructure',
  'Configure deployment networking',
  'Prepare the server',
  'Run deployment commands',
  'Verify the deployed application',
];

const CLOUDWISE_CANNOT = [
  'Billing management',
  'Payment information',
  'AWS account password',
  'Unrelated AWS services',
];

/* ------------------------------------------------------------------ */
/* Small presentational helpers                                       */

/**
 * IAM Create Policy expects a complete policy document.
 * Older backend responses may contain only the Statement array, so normalize
 * both shapes before displaying or copying the policy.
 */
const normalizeIamPolicy = (value: string): string => {
  const raw = String(value || '').trim();
  if (!raw) return '';

  try {
    const parsed = JSON.parse(raw);

    if (Array.isArray(parsed)) {
      return JSON.stringify(
        {
          Version: '2012-10-17',
          Statement: parsed,
        },
        null,
        2,
      );
    }

    if (parsed && typeof parsed === 'object') {
      return JSON.stringify(parsed, null, 2);
    }

    return raw;
  } catch {
    return raw;
  }
};

/* ------------------------------------------------------------------ */

const Eyebrow: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
    {children}
  </p>
);

interface CopyChipProps {
  text: string;
  field: string;
  copiedField: string | null;
  onCopy: (text: string, field: string) => void;
  label?: string;
}

const CopyChip: React.FC<CopyChipProps> = ({
  text,
  field,
  copiedField,
  onCopy,
  label,
}) => {
  const copied = copiedField === field;
  return (
    <button
      type="button"
      onClick={() => onCopy(text, field)}
      className={`inline-flex shrink-0 items-center gap-1 rounded-lg border px-2 py-1 text-[11px] font-bold transition-colors ${
        copied
          ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
          : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20'
      }`}
    >
      {copied ? <Check size={12} /> : <Copy size={12} />}
      <span>{copied ? 'Copied' : label || 'Copy'}</span>
    </button>
  );
};

interface PolicyBlockProps {
  field: string;
  value: string;
  open: boolean;
  onToggle: () => void;
  toggleLabel?: string;
  copiedField: string | null;
  onCopy: (text: string, field: string) => void;
}

const PolicyBlock: React.FC<PolicyBlockProps> = ({
  field,
  value,
  open,
  onToggle,
  toggleLabel,
  copiedField,
  onCopy,
}) => (
  <div className="space-y-2">
    <button
      type="button"
      onClick={onToggle}
      className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-slate-400 transition-colors hover:text-emerald-300"
    >
      <ChevronDown
        size={13}
        className={`transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
      />
      <span>{open ? 'Hide technical policy' : toggleLabel || 'View technical policy'}</span>
    </button>
    {open && (
      <div className="space-y-2 rounded-2xl border border-slate-800 bg-[#05080D]/80 p-3">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
            JSON policy
          </span>
          <CopyChip
            text={value}
            field={field}
            copiedField={copiedField}
            onCopy={onCopy}
          />
        </div>
        <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-all font-mono text-[10px] leading-relaxed text-emerald-200">
          {value}
        </pre>
      </div>
    )}
  </div>
);

interface BulletListProps {
  tone: 'can' | 'cannot';
  items: string[];
}

const BulletList: React.FC<BulletListProps> = ({ tone, items }) => (
  <ul className="space-y-1.5">
    {items.map((item) => (
      <li key={item} className="flex items-start gap-2 text-xs text-slate-300">
        {tone === 'can' ? (
          <Check size={13} className="mt-0.5 shrink-0 text-emerald-400" />
        ) : (
          <X size={13} className="mt-0.5 shrink-0 text-rose-400" />
        )}
        <span>{item}</span>
      </li>
    ))}
  </ul>
);

/* ------------------------------------------------------------------ */
/* Page                                                               */
/* ------------------------------------------------------------------ */

export const ConnectAws: React.FC = () => {
  const navigate = useNavigate();
  const { user, showToast } = useCloudWise();

  const [connection, setConnection] = useState<AwsConnectionInfo | null>(null);
  const [info, setInfo] = useState<ConnectInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [phase, setPhase] = useState<Phase>('idle');
  const [running, setRunning] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [connectError, setConnectError] = useState<ConnectError | null>(null);
  const [roleArn, setRoleArn] = useState('');
  const [region, setRegion] = useState('');
  const [regionOpen, setRegionOpen] = useState(false);
  const [regionQuery, setRegionQuery] = useState('');
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [verifySteps, setVerifySteps] = useState<VerifyStep[]>(BASE_VERIFY_STEPS);
  const [openedAws, setOpenedAws] = useState(false);
  const [showTrust, setShowTrust] = useState(false);
  const [showPermissions, setShowPermissions] = useState(false);
  const [showHowItWorks, setShowHowItWorks] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const loadConnection = async () => {
    try {
      const res = await fetch('/api/aws/connection', { headers: authHeaders() });
      const data = await res.json();
      if (data.success) {
        setConnection(data.data);
        if (data.data.connected && data.data.roleArn && !roleArn) {
          setRoleArn(data.data.roleArn);
        }
        if (data.data.region && !region) {
          setRegion(data.data.region);
        }
      }
    } catch (err) {
      console.error('Failed to load AWS connection:', err);
    }
  };

  const loadInfo = async () => {
    try {
      const res = await fetch('/api/aws/connect-info', { headers: authHeaders() });
      const data = await res.json();
      if (data.success) {
        setInfo(data.data);
        if (!region && data.data.defaultRegion) {
          setRegion(data.data.defaultRegion);
        }
      }
    } catch (err) {
      console.error('Failed to load AWS connect info:', err);
    }
  };

  useEffect(() => {
    if (!user) {
      setLoading(false);
      return;
    }
    (async () => {
      await Promise.all([loadConnection(), loadInfo()]);
      setLoading(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const copyText = async (text: string, field: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedField(field);
      showToast('Copied to clipboard', 'success');
      setTimeout(() => setCopiedField(null), 2000);
    } catch {
      showToast('Copy failed — select the text manually', 'error');
    }
  };

  const scrollToId = (id: string) => {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const postJson = async (url: string, body: Record<string, unknown>) => {
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify(body),
      });
      const payload = await res.json().catch(() => ({}));
      return { ok: res.ok && payload?.success !== false, payload };
    } catch (err) {
      return {
        ok: false,
        payload: {
          error: `CloudWise could not reach the server: ${
            err instanceof Error ? err.message : err
          }`,
          errorKind: 'platform',
        },
      };
    }
  };

  const setVerifyStep = (key: string, patch: Partial<VerifyStep>) => {
    setVerifySteps((prev) =>
      prev.map((step) => (step.key === key ? { ...step, ...patch } : step)),
    );
  };

  // Every step below is backed by a real backend / AWS operation. Status
  // only ever changes when a request finishes — there are no fake timers.
  const runVerification = async () => {
    const arn = roleArn.trim();
    const reg = region.trim();

    if (!ARN_RE.test(arn)) {
      setConnectError({
        message: 'Enter the IAM role ARN you created in your AWS account.',
        kind: 'format',
      });
      setPhase('setup');
      scrollToId('step-connect');
      return;
    }
    if (!reg) {
      setConnectError({
        message: 'Choose the AWS region where you want your application to run.',
        kind: 'region',
      });
      setPhase('setup');
      scrollToId('step-connect');
      return;
    }

    setPhase('verifying');
    setRunning(true);
    setConnectError(null);
    setVerifySteps(BASE_VERIFY_STEPS.map((step) => ({ ...step })));

    try {
      // 1 + 2 — one real STS AssumeRole + GetCallerIdentity round trip.
      setVerifyStep('role', { status: 'running' });
      setVerifyStep('access', { status: 'running' });
      const identity = await postJson('/api/aws/verify', {
        roleArn: arn,
        region: reg,
        scope: 'identity',
      });
      if (!identity.ok) throw identity.payload;
      const accountId = identity.payload?.data?.accountId || '';
      setVerifyStep('role', { status: 'done', detail: 'Role found and assumed' });
      setVerifyStep('access', {
        status: 'done',
        detail: accountId ? `Account ${accountId}` : 'Access confirmed',
      });

      // 3 — real permission probes (DryRun, read-only, nothing created).
      setVerifyStep('permissions', { status: 'running' });
      const perms = await postJson('/api/aws/verify', {
        roleArn: arn,
        region: reg,
        scope: 'permissions',
      });
      if (!perms.ok) throw perms.payload;
      const permData = perms.payload?.data || {};
      if (permData.ready === false) {
        const missing: string[] = permData.missing || [];
        throw {
          error: `Your role is missing deployment permissions (${missing.join(
            ', ',
          )}). Re-copy the permissions policy CloudWise generated and attach it to your role.`,
          errorKind: 'permissions',
          technical: missing.join(', '),
        };
      }
      setVerifyStep('permissions', {
        status: 'done',
        detail: `${permData.passed} of ${permData.total} deployment permissions verified`,
      });

      // 4 — real availability-zone + inventory read in the chosen region.
      setVerifyStep('region', { status: 'running' });
      const regionCheck = await postJson('/api/aws/verify', {
        roleArn: arn,
        region: reg,
        scope: 'region',
      });
      if (!regionCheck.ok) throw regionCheck.payload;
      setVerifyStep('region', {
        status: 'done',
        detail: `${reg} is available`,
      });

      // 5 — final server-side validation + activation.
      setVerifyStep('ready', { status: 'running' });
      const connect = await postJson('/api/aws/connect', {
        roleArn: arn,
        region: reg,
      });
      if (!connect.ok) throw connect.payload;
      setVerifyStep('ready', { status: 'done', detail: 'Connection saved' });

      showToast('AWS account connected.', 'success');
      await loadConnection();
      setPhase('idle');
    } catch (err) {
      const payload =
        err && typeof err === 'object' && 'error' in (err as Record<string, unknown>)
          ? (err as Record<string, string>)
          : {
              error: 'AWS connection failed. CloudWise could not verify your role.',
              errorKind: 'trust',
            };
      setVerifySteps((prev) =>
        prev.map((step) =>
          step.status === 'running' ? { ...step, status: 'failed' } : step,
        ),
      );
      setConnectError({
        message: payload.error || 'AWS connection failed.',
        kind: payload.errorKind || 'trust',
        technical: payload.technical || '',
      });
    } finally {
      setRunning(false);
    }
  };

  const handleDisconnect = async () => {
    setDisconnecting(true);
    try {
      const res = await fetch('/api/aws/disconnect', {
        method: 'POST',
        headers: authHeaders(),
      });
      const data = await res.json();
      if (data.success) {
        showToast('AWS account disconnected. No cloud resources were changed.', 'info');
        setConnection({ connected: false });
        setPhase('idle');
        setConnectError(null);
        setVerifySteps(BASE_VERIFY_STEPS.map((step) => ({ ...step })));
        await loadInfo();
      }
    } catch (err) {
      showToast(`Disconnect failed: ${err}`, 'error');
    } finally {
      setDisconnecting(false);
    }
  };

  const openAwsConsole = () => {
    window.open(AWS_CONSOLE_ROLE_URL, '_blank', 'noopener,noreferrer');
    setOpenedAws(true);
    setTimeout(() => scrollToId('step-permission'), 150);
  };

  const viewFix = () => {
    const kind = connectError?.kind || 'trust';
    setPhase('setup');
    if (kind === 'format' || kind === 'region') {
      scrollToId('step-connect');
      return;
    }
    if (kind === 'permissions') {
      setShowPermissions(true);
    } else {
      setShowTrust(true);
    }
    scrollToId('step-permission');
  };

  const handleVerifyAgain = () => {
    setConnectError(null);
    if (ARN_RE.test(roleArn.trim())) {
      void runVerification();
      return;
    }
    setPhase('setup');
    scrollToId('step-connect');
  };

  const isConnected = !!connection?.connected;
  const arnTrimmed = roleArn.trim();
  const arnValid = ARN_RE.test(arnTrimmed);
  const arnTouched = arnTrimmed.length > 0;
  const setupIndex = phase === 'verifying' ? 3 : arnValid ? 2 : openedAws ? 1 : 0;
  const trustedAccountId = info?.trustedAccountId || '038658707850';
  const roleShortName = (connection?.roleArn || arnTrimmed || '').split('/').pop() || '—';
  const permissionsPolicyJson = normalizeIamPolicy(`{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudWiseEC2Describe",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeInstanceStatus",
        "ec2:DescribeImages",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeVpcs",
        "ec2:DescribeSubnets",
        "ec2:DescribeAvailabilityZones",
        "ec2:DescribeKeyPairs",
        "ec2:DescribeTags",
        "ec2:DescribeVolumes",
        "ec2:DescribeIamInstanceProfileAssociations"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWiseElasticIp",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeAddresses",
        "ec2:AllocateAddress",
        "ec2:AssociateAddress",
        "ec2:DisassociateAddress",
        "ec2:ReleaseAddress"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWiseEC2Lifecycle",
      "Effect": "Allow",
      "Action": [
        "ec2:RunInstances",
        "ec2:StartInstances",
        "ec2:StopInstances",
        "ec2:RebootInstances",
        "ec2:TerminateInstances",
        "ec2:CreateTags",
        "ec2:ModifyInstanceAttribute"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWiseSecurityGroupConfig",
      "Effect": "Allow",
      "Action": [
        "ec2:CreateSecurityGroup",
        "ec2:AuthorizeSecurityGroupIngress",
        "ec2:AuthorizeSecurityGroupEgress",
        "ec2:RevokeSecurityGroupIngress",
        "ec2:RevokeSecurityGroupEgress"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWiseIAMRead",
      "Effect": "Allow",
      "Action": [
        "iam:GetRole",
        "iam:GetInstanceProfile",
        "iam:ListInstanceProfiles",
        "iam:ListRoles",
        "iam:ListRolePolicies",
        "iam:ListAttachedRolePolicies"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWiseManageEC2SSMRole",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:PutRolePolicy",
        "iam:DeleteRolePolicy",
        "iam:UpdateAssumeRolePolicy"
      ],
      "Resource": "arn:aws:iam::*:role/cloudwise-ec2-*"
    },
    {
      "Sid": "CloudWiseManageEC2SSMInstanceProfile",
      "Effect": "Allow",
      "Action": [
        "iam:CreateInstanceProfile",
        "iam:DeleteInstanceProfile",
        "iam:AddRoleToInstanceProfile",
        "iam:RemoveRoleFromInstanceProfile"
      ],
      "Resource": "arn:aws:iam::*:instance-profile/cloudwise-ec2-*"
    },
    {
      "Sid": "CloudWisePassInstanceRole",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::*:role/cloudwise-ec2-*",
      "Condition": {
        "StringEquals": {
          "iam:PassedToService": "ec2.amazonaws.com"
        }
      }
    },
    {
      "Sid": "CloudWiseReadPublicAmiParameter",
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter",
        "ssm:GetParameters"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWiseSsmContainerDeploy",
      "Effect": "Allow",
      "Action": [
        "ssm:SendCommand",
        "ssm:GetCommandInvocation",
        "ssm:ListCommands",
        "ssm:DescribeInstanceInformation",
        "ssm:DescribeInstanceAssociations"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWiseTagging",
      "Effect": "Allow",
      "Action": [
        "ec2:CreateTags"
      ],
      "Resource": "*"
    }
  ]
}`);
  const trustPolicyJson = normalizeIamPolicy(info?.trustPolicy || "");

  const regionLabel = (() => {
    const found = AWS_REGIONS.find((r) => r.code === region);
    return found ? `${found.name} (${found.code})` : region || '';
  })();

  const regionOptions = AWS_REGIONS.filter((r) => {
    const q = regionQuery.trim().toLowerCase();
    if (!q) return true;
    return r.code.toLowerCase().includes(q) || r.name.toLowerCase().includes(q);
  });

  const lastVerified = (() => {
    const iso = connection?.connectedAt;
    if (!iso) return 'Just now';
    const diff = Date.now() - new Date(iso).getTime();
    if (Number.isNaN(diff) || diff < 60_000) return 'Just now';
    return new Date(iso).toLocaleString();
  })();

  if (!user) {
    return (
      <div className="min-h-screen max-w-3xl mx-auto px-4 py-16 text-center space-y-6">
        <div className="glass-panel p-10 rounded-3xl border border-slate-800 space-y-4">
          <Cloud className="w-10 h-10 text-emerald-400 mx-auto" />
          <h1 className="text-2xl font-extrabold text-white">Connect your AWS account</h1>
          <p className="text-sm text-slate-400">
            Sign in to authorize CloudWise to deploy into your AWS account.
          </p>
          <button
            onClick={() => navigate('/auth')}
            className="px-6 py-3 rounded-xl bg-gradient-to-r from-emerald-400 to-blue-600 text-slate-950 font-bold text-sm"
          >
            Sign In / Register
          </button>
        </div>
      </div>
    );
  }

  /* ---------------------------------------------------------------- */
  /* Verification checklist (real backend calls only)                 */
  /* ---------------------------------------------------------------- */
  const verificationPanel = (
    <div className="space-y-5">
      <div className="space-y-1.5">
        <h3 className="text-sm font-bold text-white">Connecting to AWS</h3>
        <p className="text-xs text-slate-400">
          Each line below turns green only when that check has really run against
          your AWS account.
        </p>
      </div>

      <ul className="space-y-2">
        {verifySteps.map((step) => (
          <li
            key={step.key}
            className={`flex items-start gap-3 rounded-2xl border px-4 py-3 transition-colors ${
              step.status === 'done'
                ? 'border-emerald-500/30 bg-emerald-500/5'
                : step.status === 'failed'
                  ? 'border-rose-500/40 bg-rose-500/10'
                  : step.status === 'running'
                    ? 'border-emerald-500/40 bg-emerald-500/5'
                    : 'border-slate-800 bg-[#080D14]/40'
            }`}
          >
            <span className="mt-0.5 shrink-0">
              {step.status === 'done' && (
                <CheckCircle2 size={16} className="text-emerald-400" />
              )}
              {step.status === 'running' && (
                <Loader2 size={16} className="animate-spin text-emerald-300" />
              )}
              {step.status === 'failed' && <X size={16} className="text-rose-400" />}
              {step.status === 'pending' && (
                <span className="block h-3.5 w-3.5 rounded-full border border-slate-600" />
              )}
            </span>
            <span className="min-w-0 flex-1">
              <span
                className={`block text-xs font-semibold ${
                  step.status === 'failed'
                    ? 'text-rose-200'
                    : step.status === 'pending'
                      ? 'text-slate-500'
                      : 'text-white'
                }`}
              >
                {step.label}
              </span>
              {step.detail && (
                <span className="mt-0.5 block break-all text-[11px] text-slate-400">
                  {step.detail}
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>

      {connectError && (
        <div className="rounded-2xl border border-rose-500/40 bg-rose-500/10 p-4 space-y-3">
          <div className="flex items-start gap-2.5">
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-rose-300" />
            <div className="space-y-1">
              <p className="text-xs font-bold text-rose-200">AWS connection failed</p>
              <p className="text-xs leading-relaxed text-rose-100/90">
                {connectError.message}
              </p>
              <p className="text-[11px] leading-relaxed text-rose-200/70">
                Possible reason: {ERROR_HINTS[connectError.kind] || ERROR_HINTS.trust}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={viewFix}
              className="rounded-lg bg-rose-500/20 px-3 py-1.5 text-[11px] font-bold text-rose-100 transition-colors hover:bg-rose-500/30"
            >
              View Fix
            </button>
            <button
              type="button"
              onClick={() => void runVerification()}
              disabled={running}
              className="rounded-lg border border-slate-600 bg-[#080D14] px-3 py-1.5 text-[11px] font-bold text-slate-200 transition-colors hover:bg-slate-800 disabled:opacity-50"
            >
              Try Again
            </button>
          </div>
          {connectError.technical && (
            <details className="rounded-xl border border-slate-700/70 bg-[#05080D]/70 p-2.5">
              <summary className="cursor-pointer text-[10px] font-bold uppercase tracking-wider text-slate-500">
                Technical details (debugging)
              </summary>
              <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-all font-mono text-[10px] text-slate-400">
                {connectError.technical}
              </pre>
            </details>
          )}
        </div>
      )}
    </div>
  );

  /* ---------------------------------------------------------------- */
  /* Success state                                                     */
  /* ---------------------------------------------------------------- */
  const successPanel = (
    <div className="space-y-6">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 border border-emerald-500/40">
          <CheckCircle2 size={18} className="text-emerald-300" />
        </span>
        <div className="space-y-1">
          <h3 className="text-base font-extrabold text-white">AWS connected</h3>
          <p className="text-xs leading-relaxed text-slate-400">
            CloudWise can now deploy applications to this AWS account.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-2xl border border-slate-800 bg-[#080D14]/50 p-3.5">
          <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-500">
            AWS Account
          </span>
          <p className="mt-1 font-mono text-sm font-bold text-white">
            {connection?.accountId || '—'}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-[#080D14]/50 p-3.5">
          <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-500">
            Region
          </span>
          <p className="mt-1 font-mono text-sm font-bold text-white">
            {connection?.region || '—'}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-[#080D14]/50 p-3.5">
          <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-500">
            Role
          </span>
          <p className="mt-1 truncate font-mono text-sm font-bold text-emerald-300">
            {roleShortName}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-[#080D14]/50 p-3.5">
          <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-500">
            Access
          </span>
          <p className="mt-1 text-sm font-bold text-white">Temporary STS credentials</p>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-[#080D14]/50 p-3.5 sm:col-span-2">
          <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-500">
            Last verified
          </span>
          <p className="mt-1 text-sm font-bold text-white">{lastVerified}</p>
        </div>
      </div>

      <ul className="space-y-1.5">
        {[
          'AWS authorization verified',
          'Deployment permissions verified',
          'Region available',
          'CloudWise is ready',
        ].map((line) => (
          <li key={line} className="flex items-center gap-2 text-xs text-emerald-300">
            <Check size={14} className="shrink-0" />
            <span>{line}</span>
          </li>
        ))}
      </ul>

      <div className="rounded-2xl border border-emerald-500/25 bg-emerald-500/5 p-4">
        <p className="text-xs leading-relaxed text-emerald-100/90">
          You don't need to configure EC2, Docker, networking, SSM, or servers
          manually. CloudWise handles the deployment infrastructure automatically.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => navigate('/deployment')}
          className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-emerald-400 to-blue-600 px-5 py-3 text-sm font-bold text-slate-950 shadow-lg shadow-emerald-500/20 transition-all hover:from-emerald-300 hover:to-blue-500"
        >
          <span>Continue to Deployment</span>
          <ArrowRight size={16} />
        </button>
        <button
          type="button"
          onClick={() => void handleDisconnect()}
          disabled={disconnecting}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-[#080D14] px-4 py-3 text-xs font-semibold text-slate-300 transition-colors hover:border-rose-500/40 hover:text-rose-300 disabled:opacity-50"
        >
          <Unplug size={14} />
          <span>{disconnecting ? 'Disconnecting…' : 'Disconnect AWS'}</span>
        </button>
      </div>
    </div>
  );

  /* ---------------------------------------------------------------- */
  /* Hero (before setup starts)                                        */
  /* ---------------------------------------------------------------- */
  const heroPanel = (
    <div className="space-y-7">
      <div className="space-y-2 text-center">
        <p className="text-sm font-semibold text-white">
          Connect your AWS account once. After that, CloudWise can automatically
          prepare the server and deploy your applications.
        </p>
        <p className="text-xs text-slate-500">
          One-time authorization · No access keys · No servers to configure
        </p>
      </div>

      <div className="flex flex-col items-center justify-center gap-3 sm:flex-row">
        <div className="flex w-full items-center gap-3 rounded-2xl border border-slate-800 bg-[#080D14]/50 px-4 py-3 sm:w-auto">
          <Github size={18} className="shrink-0 text-slate-300" />
          <span className="text-xs font-semibold text-slate-200">GitHub Repository</span>
        </div>
        <ArrowRight size={16} className="shrink-0 rotate-90 text-slate-500 sm:rotate-0" />
        <div className="flex w-full items-center gap-3 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 sm:w-auto">
          <Cloud size={18} className="shrink-0 text-emerald-300" />
          <span className="text-xs font-semibold text-emerald-200">CloudWise</span>
        </div>
        <ArrowRight size={16} className="shrink-0 rotate-90 text-slate-500 sm:rotate-0" />
        <div className="flex w-full items-center gap-3 rounded-2xl border border-slate-800 bg-[#080D14]/50 px-4 py-3 sm:w-auto">
          <Server size={18} className="shrink-0 text-emerald-300" />
          <span className="text-xs font-semibold text-slate-200">Your AWS Account</span>
        </div>
      </div>

      <div className="space-y-2.5">
        <Eyebrow>What you'll need</Eyebrow>
        <div className="flex items-start gap-3 rounded-2xl border border-slate-800 bg-[#080D14]/40 p-4">
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-emerald-500/10 border border-emerald-500/30">
            <Cloud size={15} className="text-emerald-300" />
          </span>
          <div>
            <p className="text-xs font-bold text-white">AWS account</p>
            <p className="mt-0.5 text-xs leading-relaxed text-slate-400">
              An AWS account where you want CloudWise to deploy your application.
            </p>
          </div>
        </div>
      </div>

      <button
        type="button"
        onClick={() => setPhase('setup')}
        className="w-full rounded-xl bg-gradient-to-r from-emerald-400 to-blue-600 px-6 py-3.5 text-sm font-bold text-slate-950 shadow-lg shadow-emerald-500/20 transition-all hover:from-emerald-300 hover:to-blue-500 sm:w-auto"
      >
        Start AWS Setup
      </button>
    </div>
  );

  /* ---------------------------------------------------------------- */
  /* Setup workspace                                                   */
  /* ---------------------------------------------------------------- */
  const setupPanel = (
    <div className="space-y-8">
      {/* Compact progress */}
      <div className="flex flex-wrap items-center gap-1.5">
        {SETUP_STEPS.map((label, idx) => {
          const state =
            idx < setupIndex ? 'done' : idx === setupIndex ? 'active' : 'todo';
          return (
            <React.Fragment key={label}>
              <span
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider transition-colors ${
                  state === 'done'
                    ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
                    : state === 'active'
                      ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
                      : 'border-slate-700 bg-[#080D14]/60 text-slate-500'
                }`}
              >
                {state === 'done' ? <Check size={11} /> : <span>{idx + 1}</span>}
                <span>{label}</span>
              </span>
              {idx < SETUP_STEPS.length - 1 && (
                <ChevronDown
                  size={12}
                  className="-rotate-90 text-slate-600"
                  aria-hidden
                />
              )}
            </React.Fragment>
          );
        })}
      </div>

      {/* ---------- Account step ---------- */}
      <section className="space-y-4">
        <div className="space-y-1">
          <Eyebrow>Step 1 · Account</Eyebrow>
          <h3 className="text-sm font-extrabold text-white">Give CloudWise permission</h3>
          <p className="text-xs leading-relaxed text-slate-400">
            CloudWise needs permission to create the infrastructure required to run
            your application.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="rounded-2xl border border-emerald-500/25 bg-emerald-500/5 p-4 space-y-2.5">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-emerald-300">
              You will
            </p>
            <BulletList tone="can" items={YOU_WILL} />
          </div>
          <div className="rounded-2xl border border-rose-500/25 bg-rose-500/5 p-4 space-y-2.5">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-rose-300">
              You won't
            </p>
            <BulletList tone="cannot" items={YOU_WONT} />
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-[#080D14]/40 p-4 space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1">
              <p className="text-xs font-bold text-white">Step 1 — Open AWS</p>
              <p className="text-xs text-slate-400">
                Open your AWS account in a new tab. We'll guide you through exactly
                what to select.
              </p>
            </div>
            <button
              type="button"
              onClick={openAwsConsole}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-3.5 py-2 text-xs font-bold text-emerald-200 transition-colors hover:bg-emerald-500/20"
            >
              <span>Open AWS Console</span>
              <ExternalLink size={13} />
            </button>
          </div>
          <p className="flex items-start gap-1.5 text-[11px] text-slate-500">
            <Info size={13} className="mt-px shrink-0" />
            <span>Keep this CloudWise tab open. You'll return here after creating the role.</span>
          </p>
        </div>
      </section>

      {/* ---------- Permission step ---------- */}
      <section id="step-permission" className="space-y-4 scroll-mt-24">
        <div className="space-y-1">
          <Eyebrow>Step 2 · Permission</Eyebrow>
          <h3 className="text-sm font-extrabold text-white">Create your CloudWise role</h3>
          <p className="text-xs leading-relaxed text-slate-400">
            In AWS, create a role that allows CloudWise to request temporary deployment
            access. <span className="text-slate-500">Technical term: IAM role.</span>
          </p>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-[#080D14]/40 p-4">
          <ol className="space-y-3">
            <li className="flex items-start gap-3">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-slate-800 text-[10px] font-bold text-slate-300">
                1
              </span>
              <div className="min-w-0">
                <p className="text-[11px] text-slate-500">Go to</p>
                <p className="font-mono text-xs text-emerald-200">
                  IAM → Roles → Create role
                </p>
              </div>
            </li>
            <li className="flex items-start gap-3">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-slate-800 text-[10px] font-bold text-slate-300">
                2
              </span>
              <div>
                <p className="text-[11px] text-slate-500">Choose</p>
                <p className="text-xs font-semibold text-white">AWS account</p>
              </div>
            </li>
            <li className="flex items-start gap-3">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-slate-800 text-[10px] font-bold text-slate-300">
                3
              </span>
              <div>
                <p className="text-[11px] text-slate-500">Choose</p>
                <p className="text-xs font-semibold text-white">Another AWS account</p>
              </div>
            </li>
            <li className="flex flex-wrap items-start gap-3">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-slate-800 text-[10px] font-bold text-slate-300">
                4
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[11px] text-slate-500">
                  Enter this CloudWise account ID
                </p>
                <div className="mt-1 flex items-center gap-2 rounded-xl border border-slate-700 bg-[#05080D] px-3 py-2">
                  <span className="min-w-0 flex-1 break-all font-mono text-xs font-bold text-white">
                    {trustedAccountId}
                  </span>
                  <CopyChip
                    text={trustedAccountId}
                    field="account"
                    copiedField={copiedField}
                    onCopy={copyText}
                  />
                </div>
              </div>
            </li>
          </ol>
          <p className="mt-3 rounded-xl bg-[#05080D]/70 p-3 text-[11px] leading-relaxed text-slate-400">
            CloudWise uses this account to request temporary access. Your AWS account
            remains yours.
          </p>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-[#080D14]/40 p-4 space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-[11px] text-slate-500">Role name</p>
              <p className="font-mono text-xs font-bold text-white">
                {RECOMMENDED_ROLE_NAME}
              </p>
            </div>
            <CopyChip
              text={RECOMMENDED_ROLE_NAME}
              field="rolename"
              copiedField={copiedField}
              onCopy={copyText}
            />
          </div>
          <p className="text-[11px] text-slate-500">
            You can use another name, but {RECOMMENDED_ROLE_NAME} is recommended.
          </p>
        </div>

        {/* Trust policy */}
        <div className="rounded-2xl border border-slate-800 bg-[#080D14]/40 p-4 space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1">
              <p className="text-xs font-bold text-white">Trust policy</p>
              <p className="text-xs text-slate-400">
                Add this policy to tell AWS that CloudWise is allowed to request access.
              </p>
            </div>
            <button
              type="button"
              onClick={() => void copyText(trustPolicyJson, 'trust')}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-xl bg-emerald-500 px-3.5 py-2 text-xs font-bold text-slate-950 transition-colors hover:bg-emerald-400"
            >
              {copiedField === 'trust' ? <Check size={13} /> : <Copy size={13} />}
              <span>{copiedField === 'trust' ? 'Copied' : 'Copy Trust Policy'}</span>
            </button>
          </div>
          <PolicyBlock
            field="trust-view"
            value={trustPolicyJson}
            open={showTrust}
            onToggle={() => setShowTrust((v) => !v)}
            copiedField={copiedField}
            onCopy={copyText}
          />
        </div>

        {/* Permissions policy */}
        <div className="rounded-2xl border border-slate-800 bg-[#080D14]/40 p-4 space-y-4">
          <div className="space-y-1">
            <p className="text-xs font-bold text-white">Deployment permissions</p>
            <p className="text-xs text-slate-400">
              These permissions allow CloudWise to create and manage the infrastructure
              needed for deployment.
          </p>
          </div>

          <div className="rounded-2xl border border-emerald-500/25 bg-emerald-500/5 p-4 space-y-4">
            <div className="flex items-start gap-3">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-emerald-500/10 border border-emerald-500/30">
                <FileJson size={15} className="text-emerald-300" />
              </span>
              <div className="min-w-0 space-y-1">
                <p className="text-xs font-extrabold text-white">
                  Create the permissions policy in AWS
                </p>
                <p className="text-[11px] leading-relaxed text-slate-400">
                  This is a separate IAM policy. Create it once, then attach it to{' '}
                  <span className="font-mono text-emerald-200">{RECOMMENDED_ROLE_NAME}</span>.
                </p>
              </div>
            </div>

            <ol className="space-y-2.5">
              {[
                'Open AWS IAM → Policies → Create policy.',
                'Select the JSON tab and remove the existing sample JSON.',
                'Paste the complete CloudWise policy shown below.',
                `For Policy name, enter exactly: ${RECOMMENDED_POLICY_NAME}.`,
                'Click Create policy.',
                `Open ${RECOMMENDED_ROLE_NAME} → Add permissions → Attach policies, then select ${RECOMMENDED_POLICY_NAME}.`,
              ].map((step, index) => (
                <li key={step} className="flex items-start gap-2.5 text-[11px] leading-relaxed text-slate-300">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-slate-800 text-[10px] font-bold text-slate-300">
                    {index + 1}
                  </span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>

            <div className="rounded-xl border border-slate-700 bg-[#05080D]/80 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                    Policy name
                  </p>
                  <p className="mt-1 font-mono text-xs font-bold text-white">
                    {RECOMMENDED_POLICY_NAME}
                  </p>
                </div>
                <CopyChip
                  text={RECOMMENDED_POLICY_NAME}
                  field="policy-name"
                  copiedField={copiedField}
                  onCopy={copyText}
                  label="Copy policy name"
                />
              </div>
            </div>

            <p className="flex items-start gap-1.5 text-[11px] leading-relaxed text-slate-500">
              <Info size={13} className="mt-px shrink-0" />
              <span>
                The policy name is only a label. The permissions come from the JSON
                document below.
              </span>
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-emerald-300">
                CloudWise can
              </p>
              <BulletList tone="can" items={CLOUDWISE_CAN} />
            </div>
            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-rose-300">
                CloudWise cannot use this role for
              </p>
              <BulletList tone="cannot" items={CLOUDWISE_CANNOT} />
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-[11px] text-slate-500">
              <FileJson size={13} className="text-emerald-400" />
              <span>Least privilege — deployment services only, never admin.</span>
            </div>
            <button
              type="button"
              onClick={() => void copyText(permissionsPolicyJson, 'perms')}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-xl bg-emerald-500 px-3.5 py-2 text-xs font-bold text-slate-950 transition-colors hover:bg-emerald-400"
            >
              {copiedField === 'perms' ? <Check size={13} /> : <Copy size={13} />}
              <span>
                {copiedField === 'perms' ? 'Copied' : 'Copy Permissions Policy'}
              </span>
            </button>
          </div>

          <div className="rounded-xl border border-slate-800 bg-[#05080D]/60 px-3 py-2.5">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
              Paste location
            </p>
            <p className="mt-1 text-[11px] leading-relaxed text-slate-400">
              AWS IAM → Policies → Create policy → JSON. Paste the entire document below.
            </p>
          </div>

          <PolicyBlock
            field="perms-view"
            value={permissionsPolicyJson}
            open={showPermissions}
            onToggle={() => setShowPermissions((v) => !v)}
            copiedField={copiedField}
            onCopy={copyText}
          />
        </div>
      </section>

      {/* ---------- Connect step ---------- */}
      <section id="step-connect" className="space-y-4 scroll-mt-24">
        <div className="space-y-1">
          <Eyebrow>Step 3 · Connect</Eyebrow>
          <h3 className="text-sm font-extrabold text-white">Connect your role</h3>
          <p className="text-xs leading-relaxed text-slate-400">
            Almost done. Go back to the role you just created in AWS and copy its ARN,
            then paste it below.
          </p>
        </div>

        <div className="rounded-2xl border border-emerald-500/25 bg-emerald-500/5 p-4 space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="role-arn" className="text-[11px] font-semibold text-slate-300">
              IAM Role ARN <span className="text-rose-400">*</span>
            </label>
            <input
              id="role-arn"
              type="text"
              value={roleArn}
              onChange={(e) => {
                setRoleArn(e.target.value);
                if (connectError?.kind === 'format') setConnectError(null);
              }}
              placeholder="arn:aws:iam::123456789012:role/CloudWiseDeployRole"
              className="w-full rounded-xl border border-slate-700 bg-[#05080D] px-4 py-3 font-mono text-xs text-white outline-none transition-colors focus:border-emerald-400"
            />
            {arnTouched && (
              <p
                className={`flex items-center gap-1.5 text-[11px] font-semibold ${
                  arnValid ? 'text-emerald-300' : 'text-rose-300'
                }`}
              >
                {arnValid ? <Check size={12} /> : <X size={12} />}
                <span>{arnValid ? 'Role ARN looks valid' : 'Invalid role ARN'}</span>
              </p>
            )}
            <p className="text-[11px] text-slate-500">
              You can find the ARN at the top of your AWS role details page.
            </p>
          </div>

          {/* Visual example of where the ARN lives in AWS */}
          <div className="rounded-xl border border-slate-800 bg-[#05080D]/80 p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                Role summary page (example)
              </span>
              <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-emerald-300">
                Copy this line
              </span>
            </div>
            <p className="text-[10px] text-slate-500">ARN</p>
            <p className="break-all rounded-md bg-emerald-500/10 px-2 py-1.5 font-mono text-[11px] text-emerald-200">
              arn:aws:iam::<span className="text-white">123456789012</span>:
              <span className="text-emerald-300">role/CloudWiseDeployRole</span>
            </p>
          </div>

          <div className="space-y-1.5">
            <label htmlFor="region-search" className="text-[11px] font-semibold text-slate-300">
              Deployment region
            </label>
            <div className="relative">
              <input
                id="region-search"
                type="text"
                role="combobox"
                aria-expanded={regionOpen}
                aria-controls="region-listbox"
                readOnly={!regionOpen}
                value={regionOpen ? regionQuery : regionLabel}
                onFocus={() => {
                  setRegionQuery('');
                  setRegionOpen(true);
                }}
                onBlur={() => setRegionOpen(false)}
                onChange={(e) => setRegionQuery(e.target.value)}
                placeholder="Search regions…"
                className="w-full rounded-xl border border-slate-700 bg-[#05080D] px-4 py-3 text-xs text-white outline-none transition-colors focus:border-emerald-400"
              />
              <ChevronDown
                size={14}
                className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-500"
              />
              {regionOpen && (
                <ul
                  id="region-listbox"
                  role="listbox"
                  className="absolute z-30 mt-1 max-h-56 w-full overflow-auto rounded-xl border border-slate-700 bg-[#05080D] py-1 shadow-2xl shadow-black/60"
                >
                  {regionOptions.length === 0 && (
                    <li className="px-3 py-2 text-[11px] text-slate-500">
                      No region matches your search.
                    </li>
                  )}
                  {regionOptions.map((r) => (
                    <li key={r.code} role="option" aria-selected={r.code === region}>
                      <button
                        type="button"
                        // onMouseDown fires before blur, so the pick is kept
                        onMouseDown={(e) => {
                          e.preventDefault();
                          setRegion(r.code);
                          setRegionOpen(false);
                          if (connectError?.kind === 'region') setConnectError(null);
                        }}
                        className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs transition-colors hover:bg-emerald-500/10 ${
                          r.code === region ? 'text-emerald-300' : 'text-slate-300'
                        }`}
                      >
                        <span>{r.name}</span>
                        <span className="font-mono text-[10px] text-slate-500">
                          {r.code}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <p className="text-[11px] text-slate-500">
              Choose the AWS region where you want your application to run.
            </p>
          </div>

          {connectError && phase !== 'verifying' && (
            <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-200">
              {connectError.message}
            </div>
          )}

          <button
            type="button"
            onClick={() => void runVerification()}
            disabled={running || !arnValid || !region}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-emerald-400 to-blue-600 px-5 py-3.5 text-sm font-bold text-slate-950 shadow-lg shadow-emerald-500/20 transition-all hover:from-emerald-300 hover:to-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {running ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                <span>Verifying…</span>
              </>
            ) : (
              <>
                <ShieldCheck size={16} />
                <span>Verify &amp; Connect AWS</span>
              </>
            )}
          </button>

          {info && !info.platformCredentialsConfigured && (
            <p className="rounded-xl border border-amber-500/25 bg-amber-500/10 p-3 text-[11px] leading-relaxed text-amber-200/90">
              Note: the CloudWise server still needs its own platform credentials to
              call AWS on your behalf. This is a server setting, never something you
              provide from your AWS account.
            </p>
          )}
        </div>
      </section>
    </div>
  );

  /* ---------------------------------------------------------------- */
  /* Right-side summary card                                           */
  /* ---------------------------------------------------------------- */
  const summaryCard = (
    <aside className="lg:sticky lg:top-6">
      <div className="glass-panel rounded-3xl border border-slate-800 p-5 space-y-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Rocket size={14} className="text-emerald-300" />
            <h3 className="text-xs font-extrabold uppercase tracking-wider text-white">
              CloudWise handles the rest
            </h3>
          </div>
          <p className="text-[11px] leading-relaxed text-slate-400">
            After AWS is connected, CloudWise runs every infrastructure step for you.
          </p>
        </div>

        <ul className="space-y-1.5">
          {CLOUDWISE_HANDLES.map((item) => (
            <li key={item} className="flex items-start gap-2 text-[11px] text-slate-300">
              <Check size={12} className="mt-0.5 shrink-0 text-emerald-400" />
              <span>{item}</span>
            </li>
          ))}
        </ul>

        <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/5 p-3">
          <p className="text-[11px] font-semibold leading-relaxed text-emerald-200">
            You only need to authorize AWS once.
          </p>
        </div>
      </div>
    </aside>
  );

  /* ---------------------------------------------------------------- */
  /* Main                                                              */
  /* ---------------------------------------------------------------- */
  return (
    <div className="min-h-screen max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-8">
      {/* Header */}
      <header className="space-y-3">
        <nav className="flex items-center gap-1.5 text-[11px] text-slate-500">
          <span>Settings</span>
          <ChevronDown size={11} className="-rotate-90" aria-hidden />
          <span>Cloud</span>
          <ChevronDown size={11} className="-rotate-90" aria-hidden />
          <span className="font-semibold text-slate-300">AWS</span>
        </nav>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2 max-w-2xl">
            <h1 className="text-2xl sm:text-4xl font-extrabold text-white">
              Connect your AWS account
            </h1>
            <p className="text-sm leading-relaxed text-slate-400">
              Give CloudWise permission to deploy and manage your applications in your
              AWS account. You stay in control of your AWS account while CloudWise uses
              temporary credentials for deployment.
            </p>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-[11px] font-bold text-emerald-300">
            <Lock size={12} />
            Secure AWS connection
          </span>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_300px] items-start">
        {/* ---------------- Left column ---------------- */}
        <div className="min-w-0 space-y-6">
          <section className="glass-panel overflow-hidden rounded-3xl border border-slate-800">
            <div className="border-b border-slate-800/80 p-6 sm:p-7 space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-300">
                  <Cloud size={11} />
                  Connect AWS
                </span>
                {isConnected && (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-300">
                    <CheckCircle2 size={11} />
                    Connected
                  </span>
                )}
              </div>
              <h2 className="text-base font-extrabold text-white">
                {isConnected
                  ? 'Your AWS connection'
                  : phase === 'verifying'
                    ? 'Verifying your AWS role'
                    : phase === 'setup'
                      ? 'AWS setup'
                      : 'Connect AWS'}
              </h2>
              <p className="text-xs leading-relaxed text-slate-400">
                Connect your AWS account once. After that, CloudWise can automatically
                prepare the server and deploy your applications.
              </p>
            </div>

            <div className="p-6 sm:p-7">
              {loading ? (
                <div className="space-y-3" aria-busy>
                  <div className="h-4 w-1/3 animate-pulse rounded bg-slate-800/80" />
                  <div className="h-20 w-full animate-pulse rounded-2xl bg-slate-800/60" />
                  <div className="h-4 w-1/2 animate-pulse rounded bg-slate-800/80" />
                </div>
              ) : isConnected ? (
                successPanel
              ) : phase === 'verifying' ? (
                verificationPanel
              ) : phase === 'setup' ? (
                setupPanel
              ) : (
                heroPanel
              )}
            </div>
          </section>

          {/* Security card */}
          <section className="glass-panel rounded-3xl border border-slate-800 p-6 space-y-4">
            <div className="flex items-center gap-2">
              <ShieldCheck size={15} className="text-emerald-300" />
              <h3 className="text-sm font-extrabold text-white">
                Your AWS access stays under your control
              </h3>
            </div>
            <ul className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
              {[
                'IAM role-based access',
                'Temporary STS credentials',
                'Unique External ID',
                'No AWS access keys stored',
                'Deployment-only permissions',
              ].map((item) => (
                <li key={item} className="flex items-start gap-2 text-xs text-slate-300">
                  <Check size={13} className="mt-0.5 shrink-0 text-emerald-400" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
            <button
              type="button"
              onClick={() => setShowHowItWorks((v) => !v)}
              className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-slate-400 transition-colors hover:text-emerald-300"
            >
              <ChevronDown
                size={13}
                className={`transition-transform duration-200 ${showHowItWorks ? 'rotate-180' : ''}`}
              />
              <span>How AWS authorization works</span>
            </button>
            {showHowItWorks && (
              <p className="rounded-2xl border border-slate-800 bg-[#05080D]/70 p-4 text-xs leading-relaxed text-slate-400">
                When you click Verify &amp; Connect, CloudWise asks AWS for a{' '}
                <span className="text-slate-200">short-lived session</span> using your
                role (a handshake called STS AssumeRole). That handshake is locked to a{' '}
                <span className="text-slate-200">unique External ID</span> generated only
                for your connection, so no other CloudWise customer can use your role.
                The temporary credentials expire on their own, are never written to disk,
                and your account password and access keys are never requested.
              </p>
            )}
          </section>

          {/* Help section */}
          <section className="glass-panel rounded-3xl border border-slate-800 p-6 space-y-4">
            <div className="flex items-center gap-2">
              <HelpCircle size={15} className="text-emerald-300" />
              <h3 className="text-sm font-extrabold text-white">
                Having trouble connecting?
              </h3>
            </div>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              {[
                {
                  title: 'Role not found',
                  body: 'Make sure the role ARN was copied from the role you just created.',
                  kind: 'format',
                },
                {
                  title: 'Access denied',
                  body: 'The CloudWise role may be missing one or more deployment permissions. Click Verify Again after updating the policy.',
                  kind: 'permissions',
                },
                {
                  title: 'External ID mismatch',
                  body: 'Use the trust policy generated specifically for this CloudWise connection.',
                  kind: 'trust',
                },
              ].map((card) => (
                <div
                  key={card.title}
                  className="rounded-2xl border border-slate-800 bg-[#080D14]/40 p-4 space-y-1.5"
                >
                  <p className="text-xs font-bold text-white">{card.title}</p>
                  <p className="text-[11px] leading-relaxed text-slate-400">
                    {card.body}
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      setPhase('setup');
                      if (card.kind === 'permissions') setShowPermissions(true);
                      else setShowTrust(true);
                      setTimeout(
                        () =>
                          scrollToId(
                            card.kind === 'format' ? 'step-connect' : 'step-permission',
                          ),
                        60,
                      );
                    }}
                    className="text-[11px] font-bold text-emerald-300 transition-colors hover:text-emerald-200"
                  >
                    Show me where →
                  </button>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={handleVerifyAgain}
                disabled={running}
                className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-4 py-2 text-xs font-bold text-emerald-200 transition-colors hover:bg-emerald-500/20 disabled:opacity-50"
              >
                <RefreshCw size={13} />
                <span>Verify Again</span>
              </button>
              {!isConnected && phase === 'idle' && (
                <button
                  type="button"
                  onClick={() => setPhase('setup')}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-[#080D14] px-4 py-2 text-xs font-semibold text-slate-300 transition-colors hover:bg-slate-800"
                >
                  <Terminal size={13} />
                  <span>Back to setup</span>
                </button>
              )}
            </div>
          </section>

          {/* Advanced / technical details */}
          <section className="glass-panel rounded-3xl border border-slate-800 p-6 space-y-4">
            <button
              type="button"
              onClick={() => setShowAdvanced((v) => !v)}
              className="flex w-full items-center justify-between gap-2 text-left"
            >
              <span className="flex items-center gap-2">
                <KeyRound size={14} className="text-slate-400" />
                <span className="text-sm font-extrabold text-white">
                  Advanced / Technical details
                </span>
              </span>
              <ChevronDown
                size={15}
                className={`text-slate-500 transition-transform duration-200 ${
                  showAdvanced ? 'rotate-180' : ''
                }`}
              />
            </button>

            {showAdvanced && (
              <div className="space-y-4">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="rounded-2xl border border-slate-800 bg-[#05080D]/70 p-3.5">
                    <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-500">
                      CloudWise AWS Account ID
                    </span>
                    <div className="mt-1 flex items-center justify-between gap-2">
                      <p className="font-mono text-xs font-bold text-white">
                        {trustedAccountId}
                      </p>
                      <CopyChip
                        text={trustedAccountId}
                        field="adv-account"
                        copiedField={copiedField}
                        onCopy={copyText}
                      />
                    </div>
                  </div>
                  <div className="rounded-2xl border border-slate-800 bg-[#05080D]/70 p-3.5">
                    <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-500">
                      External ID (unique to you)
                    </span>
                    <div className="mt-1 flex items-center justify-between gap-2">
                      <p className="min-w-0 truncate font-mono text-xs font-bold text-emerald-300">
                        {info?.externalId || connection?.externalId || '—'}
                      </p>
                      {(info?.externalId || connection?.externalId) && (
                        <CopyChip
                          text={info?.externalId || connection?.externalId || ''}
                          field="adv-external"
                          copiedField={copiedField}
                          onCopy={copyText}
                        />
                      )}
                    </div>
                  </div>
                </div>

                <div className="space-y-2">
                  <p className="text-[11px] font-bold text-slate-300">Trust Policy</p>
                  <div className="rounded-2xl border border-slate-800 bg-[#05080D] p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                        JSON
                      </span>
                      <CopyChip
                        text={trustPolicyJson}
                        field="adv-trust"
                        copiedField={copiedField}
                        onCopy={copyText}
                      />
                    </div>
                    <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-all font-mono text-[10px] leading-relaxed text-emerald-200">
                      {trustPolicyJson}
                    </pre>
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-[11px] font-bold text-slate-300">Permissions Policy</p>
                    <span className="font-mono text-[10px] text-emerald-300">
                      {RECOMMENDED_POLICY_NAME}
                    </span>
                  </div>
                  <div className="rounded-2xl border border-slate-800 bg-[#05080D] p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                        JSON
                      </span>
                      <CopyChip
                        text={permissionsPolicyJson}
                        field="adv-perms"
                        copiedField={copiedField}
                        onCopy={copyText}
                      />
                    </div>
                    <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-all font-mono text-[10px] leading-relaxed text-emerald-100">
                      {permissionsPolicyJson}
                    </pre>
                  </div>
                </div>

                {info && !info.platformCredentialsConfigured && (
                  <p className="rounded-xl border border-amber-500/25 bg-amber-500/10 p-3 text-[11px] leading-relaxed text-amber-200/90">
                    The CloudWise server has no platform deployer credentials configured
                    yet, so it cannot call sts:AssumeRole. This is configured in{' '}
                    <code className="text-white">backend/.env</code> by the operator —
                    never with your AWS keys.
                  </p>
                )}
              </div>
            )}
          </section>
        </div>

        {/* ---------------- Right column ---------------- */}
        {summaryCard}
      </div>
    </div>
  );
};

export default ConnectAws;
