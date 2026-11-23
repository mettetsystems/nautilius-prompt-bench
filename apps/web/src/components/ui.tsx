import {
  forwardRef,
  useEffect,
  useMemo,
  useRef,
  type ClipboardEvent,
  type ComponentProps,
  type ReactNode,
  type Ref,
} from "react";
import { Link } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  CodeBlock,
  CodeBlockCode,
  Content,
  Flex,
  FlexItem,
  FormGroup,
  Label,
  PageSection,
  Spinner,
  Stack,
  TextArea,
  TextInput,
  Title,
  type ButtonProps,
} from "@patternfly/react-core";

export function PageFrame({
  children,
  limited = false,
}: {
  children: ReactNode;
  limited?: boolean;
}) {
  return (
    <PageSection isWidthLimited={limited}>
      <Stack hasGutter>{children}</Stack>
    </PageSection>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <Flex
      justifyContent={{ default: "justifyContentSpaceBetween" }}
      alignItems={{ default: "alignItemsCenter" }}
      flexWrap={{ default: "wrap" }}
      spaceItems={{ default: "spaceItemsMd" }}
    >
      <FlexItem>
        <Title headingLevel="h1" size="2xl">
          {title}
        </Title>
        {subtitle && <Content component="p">{subtitle}</Content>}
      </FlexItem>
      {actions && <FlexItem>{actions}</FlexItem>}
    </Flex>
  );
}

export function Panel({
  title,
  children,
  className = "",
  component = "section",
}: {
  title?: string;
  children: ReactNode;
  className?: string;
  component?: "section" | "aside" | "div";
}) {
  return (
    <Card className={className} component={component}>
      {title && (
        <CardHeader>
          <CardTitle>{title}</CardTitle>
        </CardHeader>
      )}
      <CardBody>{children}</CardBody>
    </Card>
  );
}

export function DraftBlock({ body, label = "Draft" }: { body: string; label?: string }) {
  return (
    <Stack hasGutter>
      <Label>{label}</Label>
      <CodeBlock className="draft-code">
        <CodeBlockCode>{body}</CodeBlockCode>
      </CodeBlock>
    </Stack>
  );
}

export interface DraftHighlight {
  lineNumber: number;
  start: number;
  end: number;
}

function renderHighlightedLine(
  line: string,
  highlight: { start: number; end: number } | null,
  markRef?: Ref<HTMLElement>,
): ReactNode {
  if (!highlight || highlight.start < 0 || highlight.end <= highlight.start) {
    return line;
  }
  const start = Math.min(highlight.start, line.length);
  const end = Math.min(highlight.end, line.length);
  if (start >= end) {
    return line;
  }
  return (
    <>
      {line.slice(0, start)}
      <mark ref={markRef} className="precision-term-highlight">
        {line.slice(start, end)}
      </mark>
      {line.slice(end)}
    </>
  );
}

/** Full draft with optional character-range highlight on one line; scrolls the mark into view. */
export function HighlightedDraft({
  body,
  label = "Draft",
  highlight = null,
}: {
  body: string;
  label?: string;
  highlight?: DraftHighlight | null;
}) {
  const markRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    markRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [highlight?.lineNumber, highlight?.start, highlight?.end, body]);

  const lines = body.split("\n");

  return (
    <Card isCompact>
      <CardHeader>
        <CardTitle>{label}</CardTitle>
      </CardHeader>
      <CardBody>
        <pre className="draft-text-highlighted">
          {lines.map((line, index) => {
            const lineNumber = index + 1;
            const isTarget = highlight?.lineNumber === lineNumber;
            const lineHighlight =
              isTarget && highlight ? { start: highlight.start, end: highlight.end } : null;
            return (
              <span key={`line-${lineNumber}`} className={isTarget ? "draft-line is-active" : "draft-line"}>
                {renderHighlightedLine(line, lineHighlight, isTarget ? markRef : undefined)}
                {index < lines.length - 1 ? "\n" : null}
              </span>
            );
          })}
        </pre>
      </CardBody>
    </Card>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return <Alert variant="danger" isInline role="alert" title={message.trim() || "Request failed."} />;
}

export function WarningBanner({ message }: { message: string }) {
  return <Alert variant="warning" isInline role="status" title={message} />;
}

export function SuccessBanner({ message }: { message: string }) {
  return <Alert variant="success" isInline role="status" title={message} />;
}

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <Flex alignItems={{ default: "alignItemsCenter" }} spaceItems={{ default: "spaceItemsSm" }}>
      <Spinner size="md" aria-label={label} />
      <Content component="p">{label}</Content>
    </Flex>
  );
}

export function ButtonRow({ children }: { children: ReactNode }) {
  return (
    <Flex spaceItems={{ default: "spaceItemsSm" }} flexWrap={{ default: "wrap" }} alignItems={{ default: "alignItemsCenter" }}>
      {children}
    </Flex>
  );
}

export function LinkButton({
  to,
  children,
  variant = "primary",
  ...props
}: Omit<ButtonProps, "component"> & { to: string }) {
  const RoutedLink = useMemo(() => {
    const LinkComponent = forwardRef<HTMLAnchorElement, Omit<ComponentProps<typeof Link>, "to">>(
      (componentProps, ref) => <Link {...componentProps} to={to} ref={ref} />,
    );
    LinkComponent.displayName = "RoutedLink";
    return LinkComponent;
  }, [to]);
  return (
    <Button {...props} variant={variant} component={RoutedLink}>
      {children}
    </Button>
  );
}

export function TextField({
  id,
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  isDisabled,
  autoComplete,
  isRequired,
}: {
  id: string;
  label: ReactNode;
  value: string;
  onChange: (value: string) => void;
  type?: "text" | "password" | "url" | "search";
  placeholder?: string;
  isDisabled?: boolean;
  autoComplete?: string;
  isRequired?: boolean;
}) {
  return (
    <FormGroup label={label} fieldId={id} isRequired={isRequired}>
      <TextInput
        id={id}
        type={type}
        value={value}
        placeholder={placeholder}
        isDisabled={isDisabled}
        isRequired={isRequired}
        autoComplete={autoComplete}
        onChange={(_event, next) => onChange(next)}
      />
    </FormGroup>
  );
}

export function TextAreaField({
  id,
  label,
  value,
  onChange,
  onPaste,
  rows = 4,
  placeholder,
  isDisabled,
  isRequired,
  inputRef,
  ariaLabel,
  maxLength,
  spellCheck,
}: {
  id: string;
  label?: ReactNode;
  value: string;
  onChange: (value: string) => void;
  onPaste?: (event: ClipboardEvent<HTMLTextAreaElement>) => void;
  rows?: number;
  placeholder?: string;
  isDisabled?: boolean;
  isRequired?: boolean;
  inputRef?: Ref<HTMLTextAreaElement>;
  ariaLabel?: string;
  maxLength?: number;
  spellCheck?: boolean;
}) {
  return (
    <FormGroup label={label} fieldId={id} isRequired={isRequired}>
      <TextArea
        id={id}
        ref={inputRef}
        rows={rows}
        value={value}
        placeholder={placeholder}
        isDisabled={isDisabled}
        isRequired={isRequired}
        aria-label={ariaLabel}
        maxLength={maxLength}
        spellCheck={spellCheck}
        resizeOrientation="vertical"
        onPaste={onPaste}
        onChange={(_event, next) => onChange(next)}
      />
    </FormGroup>
  );
}
