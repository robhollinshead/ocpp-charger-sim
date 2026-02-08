import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import type { ChargerCreate } from '@/types/ocpp';
import { OCPP_VERSIONS } from '@/types/ocpp';
import { useCreateCharger } from '@/api/chargers';
import { toast } from 'sonner';

const createChargerSchema = z.object({
  connection_url: z.string().url('Must be a valid URL').min(1, 'Connection URL is required'),
  charge_point_id: z.string().min(1, 'Charge point ID is required'),
  charger_name: z.string().min(1, 'Charger name is required'),
  ocpp_version: z.enum(['1.6', '2.0.1']),
  evse_count: z.number().int().min(1).max(10),
  charge_point_vendor: z.string().min(1).default('FastCharge'),
  charge_point_model: z.string().min(1).default('Pro 150'),
  firmware_version: z.string().min(1).default('2.4.1'),
});

type CreateChargerFormValues = z.infer<typeof createChargerSchema>;

interface CreateChargerDialogProps {
  locationId: string | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateChargerDialog({
  locationId,
  open,
  onOpenChange,
}: CreateChargerDialogProps) {
  const createCharger = useCreateCharger(locationId);
  const form = useForm<CreateChargerFormValues>({
    resolver: zodResolver(createChargerSchema),
    defaultValues: {
      connection_url: '',
      charge_point_id: '',
      charger_name: '',
      ocpp_version: '1.6',
      evse_count: 1,
      charge_point_vendor: '',
      charge_point_model: '',
      firmware_version: '',
    },
  });

  async function onSubmit(values: CreateChargerFormValues) {
    if (!locationId) return;
    try {
      await createCharger.mutateAsync(values as ChargerCreate);
      toast.success('Charger created');
      form.reset({
        connection_url: '',
        charge_point_id: '',
        charger_name: '',
        ocpp_version: '1.6',
        evse_count: 1,
        charge_point_vendor: '',
        charge_point_model: '',
        firmware_version: '',
      });
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to create charger');
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add charger</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="connection_url"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Connection URL</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="e.g. wss://csms.example.com/ocpp/CP001"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="charge_point_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Charge point ID</FormLabel>
                  <FormControl>
                    <Input placeholder="e.g. CP_001" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="charger_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Charger name</FormLabel>
                  <FormControl>
                    <Input placeholder="e.g. Charger A1" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="charge_point_vendor"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Charge point vendor</FormLabel>
                  <FormControl>
                    <Input placeholder="e.g. FastCharge" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="charge_point_model"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Charge point model</FormLabel>
                  <FormControl>
                    <Input placeholder="e.g. Pro 150" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="firmware_version"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Firmware version</FormLabel>
                  <FormControl>
                    <Input placeholder="e.g. 2.4.1" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="evse_count"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Number of EVSEs</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      min={1}
                      max={10}
                      value={field.value}
                      onChange={(e) => {
                        const v = parseInt(e.target.value, 10);
                        field.onChange(isNaN(v) ? 1 : Math.min(10, Math.max(1, v)));
                      }}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="ocpp_version"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>OCPP version</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select OCPP version" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {OCPP_VERSIONS.map((v) => (
                        <SelectItem key={v} value={v}>
                          {v}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={createCharger.isPending || !locationId}>
                {createCharger.isPending ? 'Creating…' : 'Add charger'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
