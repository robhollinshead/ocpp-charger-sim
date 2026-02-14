import { useState, useRef } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useImportVehicles, getVehiclesCsvTemplateUrl, getVehiclesJsonTemplateUrl } from '@/api/import';
import { toast } from 'sonner';

interface ImportVehiclesModalProps {
  locationId: string | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ImportVehiclesModal({
  locationId,
  open,
  onOpenChange,
}: ImportVehiclesModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<{ success: unknown[]; failed: { row: unknown; error: string }[] } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const importVehicles = useImportVehicles(locationId);

  function handleClose(open: boolean) {
    if (!open) {
      setFile(null);
      setResult(null);
      onOpenChange(false);
    }
  }

  async function handleSubmit() {
    if (!locationId || !file) return;
    try {
      const data = await importVehicles.mutateAsync(file);
      setResult({ success: data.success, failed: data.failed });
      if (data.failed.length === 0) {
        toast.success(`Imported ${data.success.length} vehicle${data.success.length === 1 ? '' : 's'}`);
      } else {
        toast.info(`${data.success.length} imported, ${data.failed.length} failed`);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Import failed');
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Import vehicles</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Upload a CSV or JSON file. Format is auto-detected from the file.
        </p>
        <div className="flex flex-wrap gap-2 items-center">
          <Button type="button" variant="outline" size="sm" asChild>
            <a href={getVehiclesCsvTemplateUrl()} download="vehicles.csv">
              Download CSV template
            </a>
          </Button>
          <Button type="button" variant="outline" size="sm" asChild>
            <a href={getVehiclesJsonTemplateUrl()} download="vehicles.json">
              Download JSON template
            </a>
          </Button>
        </div>
        <div className="flex gap-2 items-center">
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.json"
            className="text-sm file:mr-2 file:py-2 file:px-4 file:rounded-md file:border-0 file:bg-primary file:text-primary-foreground"
            onChange={(e) => {
              const f = e.target.files?.[0];
              setFile(f ?? null);
              setResult(null);
            }}
          />
          <Button
            onClick={handleSubmit}
            disabled={!file || !locationId || importVehicles.isPending}
          >
            {importVehicles.isPending ? 'Importing…' : 'Import'}
          </Button>
        </div>

        {result && (
          <div className="space-y-4 border-t pt-4">
            <p className="text-sm font-medium">
              {result.success.length} imported, {result.failed.length} failed
            </p>
            {result.success.length > 0 && (
              <div>
                <p className="text-sm text-muted-foreground mb-1">Imported</p>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>name</TableHead>
                      <TableHead>idTags</TableHead>
                      <TableHead className="text-right">battery_capacity_kWh</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(result.success as { name?: string; idTags?: string[]; battery_capacity_kWh?: number }[]).map(
                      (row, i) => (
                        <TableRow key={i}>
                          <TableCell>{row.name ?? '-'}</TableCell>
                          <TableCell>{row.idTags?.length ? row.idTags.join(', ') : '-'}</TableCell>
                          <TableCell className="text-right">{row.battery_capacity_kWh ?? '-'}</TableCell>
                        </TableRow>
                      )
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
            {result.failed.length > 0 && (
              <div>
                <p className="text-sm text-destructive font-medium mb-1">Failed</p>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Error</TableHead>
                      <TableHead>Row</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {result.failed.map((item, i) => (
                      <TableRow key={i}>
                        <TableCell className="text-destructive">{item.error}</TableCell>
                        <TableCell className="max-w-[200px] truncate font-mono text-xs">
                          {JSON.stringify(item.row)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => handleClose(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
