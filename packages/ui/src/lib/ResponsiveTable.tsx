import { useState, type ReactNode, type CSSProperties } from 'react';
import { Table, Card, Stack, Group, Text, UnstyledButton } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';

export interface ResponsiveTableColumn {
  key: string;
  label: string;
  sortable?: boolean;
}

export interface ResponsiveTableProps {
  columns: ResponsiveTableColumn[];
  data: Record<string, unknown>[];
  onRowClick?: (row: Record<string, unknown>) => void;
  sortable?: boolean;
  renderCell?: (
    key: string,
    value: unknown,
    row: Record<string, unknown>
  ) => ReactNode;
  rowStyle?: (row: Record<string, unknown>) => CSSProperties | undefined;
}

type SortDirection = 'asc' | 'desc';

export function ResponsiveTable({
  columns,
  data,
  onRowClick,
  sortable = false,
  renderCell,
  rowStyle,
}: ResponsiveTableProps) {
  const isMobile = useMediaQuery('(max-width: 62em)');
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDirection>('asc');

  const handleSort = (key: string) => {
    if (!sortable) return;
    const col = columns.find((c) => c.key === key);
    if (!col?.sortable) return;
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  const sortedData = (() => {
    if (!sortKey) return data;
    return [...data].sort((a, b) => {
      const aVal = a[sortKey];
      const bVal = b[sortKey];
      if (aVal == null && bVal == null) return 0;
      if (aVal == null) return 1;
      if (bVal == null) return -1;
      if (typeof aVal === 'number' && typeof bVal === 'number') {
        return sortDir === 'asc' ? aVal - bVal : bVal - aVal;
      }
      const aStr = String(aVal);
      const bStr = String(bVal);
      return sortDir === 'asc'
        ? aStr.localeCompare(bStr)
        : bStr.localeCompare(aStr);
    });
  })();

  const sortIndicator = (key: string) => {
    if (!sortable) return null;
    const col = columns.find((c) => c.key === key);
    if (!col?.sortable) return null;
    if (sortKey !== key) return ' ↕';
    return sortDir === 'asc' ? ' ↑' : ' ↓';
  };

  if (isMobile) {
    return (
      <Stack gap="sm">
        {sortable && (
          <Group gap="xs" wrap="wrap">
            {columns
              .filter((col) => col.sortable)
              .map((col) => (
                <UnstyledButton
                  key={col.key}
                  onClick={() => handleSort(col.key)}
                  style={{
                    padding: '4px 8px',
                    borderRadius: 4,
                    border: '1px solid var(--mantine-color-default-border)',
                    background:
                      sortKey === col.key
                        ? 'var(--mantine-color-blue-light)'
                        : undefined,
                  }}
                >
                  <Text size="xs" fw={sortKey === col.key ? 600 : 400}>
                    {col.label}
                    {sortIndicator(col.key)}
                  </Text>
                </UnstyledButton>
              ))}
          </Group>
        )}
        {sortedData.map((row, idx) => (
          <Card
            key={idx}
            shadow="xs"
            padding="sm"
            radius="md"
            withBorder
            style={{
              cursor: onRowClick ? 'pointer' : 'default',
              ...rowStyle?.(row),
            }}
            onClick={() => onRowClick?.(row)}
          >
            <Stack gap={4}>
              {columns.map((col) => (
                <Group key={col.key} justify="space-between">
                  <Text size="sm" c="dimmed">
                    {col.label}
                  </Text>
                  <Text size="sm" fw={500} component="span">
                    {renderCell
                      ? renderCell(col.key, row[col.key], row)
                      : row[col.key] != null
                        ? String(row[col.key])
                        : '—'}
                  </Text>
                </Group>
              ))}
            </Stack>
          </Card>
        ))}
      </Stack>
    );
  }

  return (
    <Table striped highlightOnHover>
      <Table.Thead>
        <Table.Tr>
          {columns.map((col) => (
            <Table.Th
              key={col.key}
              style={{
                cursor: sortable && col.sortable ? 'pointer' : 'default',
                userSelect: 'none',
              }}
              onClick={() => handleSort(col.key)}
            >
              {col.label}
              {sortIndicator(col.key)}
            </Table.Th>
          ))}
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {sortedData.map((row, idx) => (
          <Table.Tr
            key={idx}
            style={{
              cursor: onRowClick ? 'pointer' : 'default',
              ...rowStyle?.(row),
            }}
            onClick={() => onRowClick?.(row)}
          >
            {columns.map((col) => (
              <Table.Td key={col.key}>
                {renderCell
                  ? renderCell(col.key, row[col.key], row)
                  : row[col.key] != null
                    ? String(row[col.key])
                    : '—'}
              </Table.Td>
            ))}
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}
