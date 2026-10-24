<script setup lang="ts">
  import { onMounted, ref } from 'vue'

  // interfaces
  interface InferenceImage {
    guid: string
    name: string
    filepath: string
    upload_group_id: string
    uploaded_at?: string
  }

  // variables
  const images = ref<InferenceImage[]>([])

  // fetch existing uploaded images, to be called on mount TODO -paginate
  const fetchImages = async () => {
    try {
      const response = await fetch('/images')
      if (response.ok) {
        images.value = await response.json()
      }
    } catch (err) {
      console.error('Failed to fetch images:', err)
    }
  }

  onMounted(() => {
    fetchImages()
  })
</script>

<template>
  <div v-if="images.length === 0">
    No images uploaded yet
  </div>
  <div>
    <div 
      v-for="img in images"
      :key="img.guid"
      ><div>
          <p class="font-medium text-slate-800">{{ img.name }}</p>
          <p class="text-xs text-slate-400 font-mono mt-0.5">Path: {{ img.filepath }}</p>
        </div>
      </div>
  </div>
</template>