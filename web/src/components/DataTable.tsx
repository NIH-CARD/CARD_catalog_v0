import { useRef, useState } from "react";
import {
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type PaginationState,
  type SortingState,
} from "@tanstack/react-table";

interface Props<T> {
  rows: T[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  columns: ColumnDef<T, any>[];
  empty?: string;
  maxHeight?: string;
  /** Rows rendered per page - large tables (Grants, Supplementary) stall the page when rendered whole. */
  pageSize?: number;
}

export function DataTable<T>({
  rows,
  columns,
  empty = "No records match the current filters.",
  maxHeight = "calc(100vh - 12rem)",
  pageSize = 1000,
}: Props<T>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize });
  const scrollRef = useRef<HTMLDivElement>(null);
  // Sorting runs over all rows, then pagination slices - a sort reorders the whole set, not one page.
  // Page index resets to 0 whenever `rows` changes (TanStack's autoResetPageIndex), e.g. on a new filter.
  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting, pagination },
    onSortingChange: setSorting,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  const pageCount = table.getPageCount();
  const first = pagination.pageIndex * pagination.pageSize;
  const goTo = (pageIndex: number) => {
    table.setPageIndex(pageIndex);
    scrollRef.current?.scrollTo({ top: 0 });
  };

  return (
    <div className="border border-slate-200 rounded bg-white overflow-hidden">
      <div ref={scrollRef} className="overflow-auto" style={{ maxHeight }}>
        <table className="min-w-full text-sm">
          <thead className="bg-slate-100 sticky top-0">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => {
                  const explicit = h.column.columnDef.size != null;
                  return (
                    <th
                      key={h.id}
                      className="text-left px-3 py-2 text-xs font-semibold text-slate-600 uppercase tracking-wide cursor-pointer select-none"
                      style={explicit ? { minWidth: h.getSize(), width: h.getSize() } : undefined}
                      onClick={h.column.getToggleSortingHandler()}
                    >
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      {{ asc: " ▲", desc: " ▼" }[h.column.getIsSorted() as string] ?? ""}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row, i) => (
              <tr
                key={row.id}
                className={i % 2 === 0 ? "bg-white" : "bg-slate-50/50"}
              >
                {row.getVisibleCells().map((c) => {
                  const explicit = c.column.columnDef.size != null;
                  return (
                    <td
                      key={c.id}
                      className="px-3 py-2 align-top"
                      style={explicit ? { minWidth: c.column.getSize(), width: c.column.getSize() } : undefined}
                    >
                      {flexRender(c.column.columnDef.cell, c.getContext())}
                    </td>
                  );
                })}
              </tr>
            ))}
            {table.getRowModel().rows.length === 0 && (
              <tr>
                <td
                  colSpan={columns.length}
                  className="text-center py-8 text-slate-500"
                >
                  {empty}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {pageCount > 1 && (
        <div className="flex items-center justify-between gap-3 border-t border-slate-200 px-3 py-2 text-xs text-slate-600">
          <span className="tabular-nums">
            Rows {(first + 1).toLocaleString()}–{Math.min(first + pagination.pageSize, rows.length).toLocaleString()} of{" "}
            {rows.length.toLocaleString()}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => goTo(0)}
              disabled={!table.getCanPreviousPage()}
              className="px-2 py-1 rounded border border-slate-200 hover:bg-slate-100 disabled:opacity-40 disabled:hover:bg-transparent"
            >
              « First
            </button>
            <button
              onClick={() => goTo(pagination.pageIndex - 1)}
              disabled={!table.getCanPreviousPage()}
              className="px-2 py-1 rounded border border-slate-200 hover:bg-slate-100 disabled:opacity-40 disabled:hover:bg-transparent"
            >
              ‹ Prev
            </button>
            <span className="px-2 tabular-nums">
              Page {(pagination.pageIndex + 1).toLocaleString()} of {pageCount.toLocaleString()}
            </span>
            <button
              onClick={() => goTo(pagination.pageIndex + 1)}
              disabled={!table.getCanNextPage()}
              className="px-2 py-1 rounded border border-slate-200 hover:bg-slate-100 disabled:opacity-40 disabled:hover:bg-transparent"
            >
              Next ›
            </button>
            <button
              onClick={() => goTo(pageCount - 1)}
              disabled={!table.getCanNextPage()}
              className="px-2 py-1 rounded border border-slate-200 hover:bg-slate-100 disabled:opacity-40 disabled:hover:bg-transparent"
            >
              Last »
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
