import { useState } from "react";
import { useParams } from "react-router-dom";
import { Button, Content, DescriptionList, DescriptionListDescription, DescriptionListGroup, DescriptionListTerm, Grid, GridItem, Stack, Title } from "@patternfly/react-core";
import { artifactFileUrl } from "../api/http";
import { useRegistryPrompt } from "../api/hooks";
import { RequirementCardPanel } from "../components/RequirementCardPanel";
import { DraftBlock, LinkButton, LoadingState, PageFrame, PageHeader, Panel } from "../components/ui";

export function RegistryDetailPage() {
  const { promptId = "" } = useParams();
  const detail = useRegistryPrompt(promptId);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>("");
  const [fileLoading, setFileLoading] = useState(false);

  async function openArtifact(filename: string) {
    setSelectedFile(filename);
    setFileLoading(true);
    try {
      const response = await fetch(artifactFileUrl(promptId, filename));
      if (!response.ok) {
        setFileContent(`Failed to load ${filename} (${response.status}).`);
        return;
      }
      const text = await response.text();
      setFileContent(text);
    } catch {
      setFileContent(`Failed to load ${filename}.`);
    } finally {
      setFileLoading(false);
    }
  }

  if (detail.isLoading) {
    return (
      <PageFrame>
        <LoadingState label="Loading prompt…" />
      </PageFrame>
    );
  }

  if (detail.isError || !detail.data) {
    return (
      <PageFrame>
        <PageHeader title="Prompt not found" />
        <LinkButton to="/registry" variant="link">
          Back to registry
        </LinkButton>
      </PageFrame>
    );
  }

  const data = detail.data;
  const metadata = data.metadata;
  const manifestFiles = data.artifact_manifest?.files ?? [];
  const artifactPaths = Object.entries(metadata.artifact_paths);

  return (
    <PageFrame>
      <PageHeader
        title={metadata.title}
        subtitle={metadata.abstract || "Finalized prompt registry entry"}
        actions={
          <LinkButton to="/registry" variant="secondary">
            Back
          </LinkButton>
        }
      />

      <Grid hasGutter>
        <GridItem md={8}>
          <Stack hasGutter>
            <Panel title="Metadata">
              <DescriptionList isCompact>
                <DescriptionListGroup>
                  <DescriptionListTerm>Prompt ID</DescriptionListTerm>
                  <DescriptionListDescription>
                    <code>{metadata.prompt_id}</code>
                  </DescriptionListDescription>
                </DescriptionListGroup>
                <DescriptionListGroup>
                  <DescriptionListTerm>Version</DescriptionListTerm>
                  <DescriptionListDescription>{metadata.version}</DescriptionListDescription>
                </DescriptionListGroup>
                <DescriptionListGroup>
                  <DescriptionListTerm>Output form</DescriptionListTerm>
                  <DescriptionListDescription>{metadata.output_form || "—"}</DescriptionListDescription>
                </DescriptionListGroup>
                {metadata.tags.length > 0 && (
                  <DescriptionListGroup>
                    <DescriptionListTerm>Tags</DescriptionListTerm>
                    <DescriptionListDescription>{metadata.tags.join(", ")}</DescriptionListDescription>
                  </DescriptionListGroup>
                )}
                {Object.keys(metadata.evaluation_scores).length > 0 && (
                  <DescriptionListGroup>
                    <DescriptionListTerm>Evaluation scores</DescriptionListTerm>
                    <DescriptionListDescription>
                      <Content component="ul">
                        {Object.entries(metadata.evaluation_scores).map(([key, value]) => (
                          <Content key={key} component="li">
                            {key}: {value}
                          </Content>
                        ))}
                      </Content>
                    </DescriptionListDescription>
                  </DescriptionListGroup>
                )}
              </DescriptionList>
            </Panel>

            <Panel title="Canonical prompt">
              <DraftBlock body={data.canonical_prompt} label="Registry canonical" />
            </Panel>

            <Panel title="Artifacts">
              {manifestFiles.length === 0 && artifactPaths.length === 0 ? (
                <Content component="p">No export artifacts linked yet.</Content>
              ) : (
                <Content component="ul">
                  {manifestFiles.map((file) => (
                    <Content key={file.name} component="li">
                      <Button variant="link" isInline onClick={() => void openArtifact(file.name)}>
                        {file.name}
                      </Button>
                      <Content component="small">
                        ({file.format}, {file.size_bytes} bytes)
                      </Content>
                      <a href={artifactFileUrl(promptId, file.name)} target="_blank" rel="noreferrer">
                        Open
                      </a>
                    </Content>
                  ))}
                  {manifestFiles.length === 0 &&
                    artifactPaths.map(([key, path]) => (
                      <Content key={key} component="li">
                        <code>{key}</code>: <code>{path}</code>
                      </Content>
                    ))}
                </Content>
              )}
              {selectedFile && (
                <div>
                  <Title headingLevel="h3" size="md">
                    {selectedFile}
                  </Title>
                  {fileLoading ? <LoadingState /> : <DraftBlock body={fileContent} label={selectedFile} />}
                </div>
              )}
            </Panel>
          </Stack>
        </GridItem>
        <GridItem md={4}>
          <RequirementCardPanel card={data.requirement_card} title="Coding dimensions" />
        </GridItem>
      </Grid>
    </PageFrame>
  );
}
