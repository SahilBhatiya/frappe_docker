// Copyright (c) 2026, Ravindu Gajanayaka
// Licensed under GPLv3. See license.txt

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useStorage } from '@vueuse/core'
import { call } from 'frappe-ui'
import type { Customer, CustomerAddress, CustomerContact, CustomerCar } from '@/types'
import type { LoyaltyData } from '@/stores/customer'

export interface CustomerInvoice {
  name: string
  posting_date: string
  grand_total: number
  status: string
  is_return: boolean
  currency: string
  total_qty: number
  outstanding_amount: number
  doctype: 'POS Invoice' | 'Sales Invoice'
}

export interface CustomerPayment {
  name: string
  posting_date: string
  payment_type: string
  mode_of_payment: string | null
  paid_amount: number
  received_amount: number
  unallocated_amount: number
  reference_no: string | null
  status: string
  company: string
  source_doctype: 'Payment Entry' | 'POS Invoice'
}

export interface CustomerTransaction extends Partial<CustomerInvoice>, Partial<CustomerPayment> {
  name: string
  posting_date: string
  type: 'invoice' | 'payment'
  amount: number
  currency?: string
}

export interface CustomerOutstanding {
  outstanding: number
  credit_limit: number
}

export const useCustomerDisplayStore = defineStore('customerDisplay', () => {
  // List state
  const customers = ref<{ name: string; customer_name: string; mobile_no: string | null; email_id: string | null; last_invoice_date?: string }[]>([])
  const recentCustomers = ref<{ name: string; customer_name: string; mobile_no: string | null; email_id: string | null; last_invoice_date?: string }[]>([])
  const topCustomers = ref<{ name: string; customer_name: string; mobile_no: string | null; email_id: string | null; }[]>([])
  const recentSearches = useStorage<string[]>('pos_prime_recent_customer_searches', [])
  const searchTerm = ref('')
  const listLoading = ref(false)

  // Detail state
  const selectedCustomer = ref<Customer | null>(null)
  const addresses = ref<CustomerAddress[]>([])
  const contacts = ref<CustomerContact[]>([])
  const loyaltyData = ref<LoyaltyData | null>(null)
  const invoices = ref<CustomerInvoice[]>([])
  const payments = ref<CustomerPayment[]>([])
  const transactions = ref<CustomerTransaction[]>([])
  const cars = ref<CustomerCar[]>([])
  const outstanding = ref<CustomerOutstanding>({ outstanding: 0, credit_limit: 0 })
  const detailLoading = ref(false)

  async function loadRecentCustomers(posProfile: string = '') {
    listLoading.value = true
    try {
      const data = await call('pos_prime.api.customers.get_recent_customers', {
        pos_profile: posProfile,
        limit: 20,
      })
      recentCustomers.value = data || []
    } catch {
      recentCustomers.value = []
    } finally {
      listLoading.value = false
    }
  }

  async function loadTopCustomers(posProfile: string = '') {
    try {
      const data = await call('pos_prime.api.customers.get_top_customers', {
        pos_profile: posProfile,
        limit: 100,
      })
      topCustomers.value = data || []
    } catch {
      topCustomers.value = []
    }
  }

  function addRecentSearch(term: string) {
    if (!term || term.trim().length < 2) return
    const searches = new Set([term.trim(), ...recentSearches.value])
    recentSearches.value = Array.from(searches).slice(0, 5)
  }

  function removeRecentSearch(term: string) {
    recentSearches.value = recentSearches.value.filter(t => t !== term)
  }

  function clearRecentSearches() {
    recentSearches.value = []
  }

  async function searchCustomers(term: string, posProfile: string = '') {
    searchTerm.value = term
    if (!term || term.length < 2) {
      customers.value = []
      return
    }
    listLoading.value = true
    try {
      const data = await call('pos_prime.api.customers.search_customers', {
        search_term: term,
        pos_profile: posProfile,
      })
      customers.value = data || []
    } catch {
      customers.value = []
    } finally {
      listLoading.value = false
    }
  }

  async function loadCustomerDetail(customerName: string, company: string = '') {
    detailLoading.value = true
    try {
      const [doc, addrData, contactData, historyData, carData, outstandingData] = await Promise.all([
        call('pos_prime.api.customers.get_customer', { customer_name: customerName }),
        call('pos_prime.api.addresses.get_customer_addresses', { customer: customerName }).catch(() => []),
        call('pos_prime.api.addresses.get_customer_contacts', { customer: customerName }).catch(() => []),
        call('pos_prime.api.customer_profile.get_customer_history', { customer: customerName, company }).catch(() => ({ invoices: [], payments: [], transactions: [] })),
        call('pos_prime.api.customers.get_customer_cars', { customer: customerName }).catch(() => []),
        call('pos_prime.api.customer_profile.get_customer_outstanding', { customer: customerName, company }).catch(() => ({ outstanding: 0, credit_limit: 0 })),
      ])

      selectedCustomer.value = {
        name: doc.name,
        customer_name: doc.customer_name,
        email_id: doc.email_id,
        mobile_no: doc.mobile_no,
        loyalty_program: doc.loyalty_program,
        loyalty_points: 0,
        territory: doc.territory,
        customer_group: doc.customer_group,
        tax_id: doc.tax_id,
      }

      addresses.value = addrData || []
      contacts.value = contactData || []
      invoices.value = historyData?.invoices || []
      payments.value = historyData?.payments || []
      transactions.value = historyData?.transactions || []
      cars.value = carData || []
      outstanding.value = outstandingData || { outstanding: 0, credit_limit: 0 }

      // Fetch loyalty if applicable
      loyaltyData.value = null
      if (doc.loyalty_program) {
        try {
          const loyalty = await call('pos_prime.api.loyalty.get_customer_loyalty', { customer: customerName })
          if (loyalty) {
            loyaltyData.value = loyalty
            selectedCustomer.value!.loyalty_points = loyalty.loyalty_points
          }
        } catch {
          // ignore
        }
      }
    } catch (e) {
      selectedCustomer.value = null
    } finally {
      detailLoading.value = false
    }
  }

  async function addCar(values: {
    registration_number: string
    make_model?: string
    current_odometer?: number
    monthly_driven?: number
    notes?: string
  }) {
    if (!selectedCustomer.value) throw new Error('No customer selected')
    const car = await call('pos_prime.api.customers.create_customer_car', {
      customer: selectedCustomer.value.name,
      ...values,
    })
    cars.value = [...cars.value, car]
    return car
  }

  async function updateCar(carName: string, values: {
    registration_number: string
    make_model?: string
    current_odometer?: number
    monthly_driven?: number
    notes?: string
  }) {
    if (!selectedCustomer.value) throw new Error('No customer selected')
    const car = await call('pos_prime.api.customers.update_customer_car', {
      customer: selectedCustomer.value.name,
      car: carName,
      ...values,
    })
    cars.value = cars.value.map((existing) => existing.name === carName ? car : existing)
    return car
  }

  function $reset() {
    customers.value = []
    recentCustomers.value = []
    searchTerm.value = ''
    listLoading.value = false
    selectedCustomer.value = null
    addresses.value = []
    contacts.value = []
    loyaltyData.value = null
    invoices.value = []
    payments.value = []
    transactions.value = []
    cars.value = []
    outstanding.value = { outstanding: 0, credit_limit: 0 }
    detailLoading.value = false
  }

  return {
    customers,
    recentCustomers,
    topCustomers,
    recentSearches,
    searchTerm,
    listLoading,
    selectedCustomer,
    addresses,
    contacts,
    loyaltyData,
    invoices,
    payments,
    transactions,
    cars,
    outstanding,
    detailLoading,
    loadRecentCustomers,
    loadTopCustomers,
    addRecentSearch,
    removeRecentSearch,
    clearRecentSearches,
    searchCustomers,
    loadCustomerDetail,
    addCar,
    updateCar,
    $reset,
  }
})
