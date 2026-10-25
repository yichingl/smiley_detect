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

  interface TaskInfo {
    guid: string
    detection_count: number
    task_status: string
  }

  interface Detection {
    id: number
    confidence: number
    x_min: number
    y_min: number
    x_max: number
    y_max: number
  }

  // variables
  const images = ref<InferenceImage[]>([])
  const expandedImages = ref<Record<string, boolean>>({})
  const imageDetails = ref<Record<string, TaskInfo[]>>({})

  // Track active detections and selected task ID per image
  const activeDetections = ref<Record<string, Detection[]>>({})
  const activeTaskId = ref<Record<string, string>>({})

  // Upload state variables
  const fileInput = ref<HTMLInputElement | null>(null)
  const selectedFile = ref<File | null>(null)
  const isUploading = ref(false)
  const uploadMessage = ref('')

  // Fetch existing uploaded images on mount / refresh
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

  // Handle file selection
  const handleFileChange = (event: Event) => {
    const target = event.target as HTMLInputElement
    if (target.files && target.files[0]) {
      selectedFile.value = target.files[0]
    }
  }

  // Upload single image via /upload-single-image/
  const uploadImage = async () => {
    if (!selectedFile.value) {
      uploadMessage.value = 'Please select a file first!'
      return
    }

    const formData = new FormData()
    formData.append('file', selectedFile.value)

    isUploading.value = true
    uploadMessage.value = ''

    try {
      const response = await fetch('/upload-single-image/', {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        throw new Error('Upload failed')
      }

      uploadMessage.value = 'Image uploaded successfully!'
      selectedFile.value = null
      if (fileInput.value) fileInput.value.value = ''

      // Refresh images list automatically after upload
      await fetchImages()
    } catch (err) {
      uploadMessage.value = 'Error uploading image. Please try again.'
      console.error(err)
    } finally {
      isUploading.value = false
    }
  }

  // Fetch tasks for a specific image GUID (used for initial expansion and manual refresh)
  const fetchTasksForImage = async (imgGuid: string) => {
    try {
      const response = await fetch(`/images/${imgGuid}/tasks`)
      if (response.ok) {
        const data = await response.json()
        imageDetails.value[imgGuid] = data.tasks || []
      } else {
        imageDetails.value[imgGuid] = []
      }
    } catch (err) {
      console.error('Failed to fetch tasks for image', err)
      imageDetails.value[imgGuid] = []
    }
  }

  // Toggle expansion and lazily fetch tasks if not loaded yet
  const toggleExpand = async (img: InferenceImage) => {
    const currentState = !!expandedImages.value[img.guid]
    expandedImages.value[img.guid] = !currentState

    if (!currentState && !imageDetails.value[img.guid]) {
      await fetchTasksForImage(img.guid)
    }
  }

  // Start a task for the image guid
  const startTaskOnImage = async (imgGuid: string) => {
    try {
      const response = await fetch(`/process-image/${imgGuid}`, { method: 'POST' })
      if (!response.ok) {
        throw new Error(`Server returned status ${response.status}`)
      }
      // Automatically refresh tasks list after starting a new task
      await fetchTasksForImage(imgGuid)
    } catch (err) {
      console.error('Failed to start processing on image:', err)
    }
  }

  // Fetch task details and detections when a task item is clicked
  const selectTaskAndFetchDetections = async (imgGuid: string, task: TaskInfo) => {
    activeTaskId.value[imgGuid] = task.guid
    try {
      const response = await fetch(`/task-details/${task.guid}`)
      if (response.ok) {
        const data = await response.json()
        activeDetections.value[imgGuid] = data.detections || []
      } else {
        activeDetections.value[imgGuid] = []
      }
    } catch (err) {
      console.error('Failed to fetch task detections:', err)
      activeDetections.value[imgGuid] = []
    }
  }

  onMounted(() => {
    fetchImages()
  })
</script>

<template>
  <main class="min-h-screen bg-slate-100 p-8">
    <div class="max-w-3xl mx-auto space-y-8">
      
      <!-- Header -->
      <header class="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
        <h1 class="text-2xl font-bold text-slate-800">Smiley Detection Dashboard</h1>
        <p class="text-sm text-slate-500 mt-1">Upload an image and view associated tasks.</p>
      </header>
      
      <!-- Upload Section -->
      <section class="bg-white p-6 rounded-xl shadow-sm border border-slate-200 space-y-4">
        <h2 class="text-lg font-semibold text-slate-700">Upload Image</h2>
        
        <div class="flex items-center space-x-4">
          <input 
            type="file" 
            ref="fileInput"
            @change="handleFileChange"
            accept="image/jpeg, image/jpg, image/png"
            class="block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 cursor-pointer"
          />
          <button 
            @click="uploadImage"
            :disabled="isUploading || !selectedFile"
            class="px-5 py-2 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition whitespace-nowrap"
          >
            {{ isUploading ? 'Uploading...' : 'Upload Image' }}
          </button>
        </div>

        <p v-if="uploadMessage" class="text-sm font-medium" :class="uploadMessage.includes('successfully') ? 'text-green-600' : 'text-red-600'">
          {{ uploadMessage }}
        </p>
      </section>

      <!-- Uploaded Images List -->
      <section class="bg-white p-6 rounded-xl shadow-sm border border-slate-200 space-y-4">
        <div class="flex justify-between items-center">
          <h2 class="text-lg font-semibold text-slate-700">Uploaded Images</h2>
          <button 
            @click="fetchImages" 
            class="px-3 py-1.5 bg-slate-100 text-slate-700 hover:bg-slate-200 rounded-lg text-xs font-semibold transition border border-slate-200 flex items-center gap-1.5"
          >
            🔄 Refresh Images
          </button>
        </div>

        <div v-if="images.length === 0" class="text-sm text-slate-400 italic">
          No images uploaded yet.
        </div>

        <div class="space-y-3">
          <div 
            v-for="img in images" 
            :key="img.guid"
            class="border border-slate-200 rounded-lg p-4 transition hover:border-blue-300 cursor-pointer bg-white"
            @click="toggleExpand(img)"
          >
            <!-- Summary Row -->
            <div class="flex justify-between items-center">
              <div>
                <p class="font-medium text-slate-800">{{ img.name }}</p>
                <p class="text-xs text-slate-400 font-mono mt-0.5">Path: {{ img.filepath }}</p>
              </div>
              <span class="text-xs font-semibold text-blue-600 bg-blue-50 px-2.5 py-1 rounded-full">
                {{ expandedImages[img.guid] ? 'Collapse' : 'Expand' }}
              </span>
            </div>

            <!-- Expanded Details -->
            <div v-if="expandedImages[img.guid]" class="mt-4 pt-4 border-t border-slate-100 space-y-4" @click.stop>
              <div class="flex gap-4 items-center">

                <!-- Image Preview & 0 Detections Label -->
                <div class="flex flex-col items-center">
                  <div class="relative inline-block">
                    <img 
                      :src="activeTaskId[img.guid] ? `/tasks/${activeTaskId[img.guid]}/rendered-image` : `/${img.filepath}`" 
                      alt="Preview" 
                      class="w-48 h-auto rounded-lg border border-slate-200 block object-cover" 
                    />
                  </div>
                  <!-- Show "0 detections" if a task is selected and detections array is empty -->
                  <div 
                    v-if="activeTaskId[img.guid] && activeDetections[img.guid] && activeDetections[img.guid].length === 0" 
                    class="text-xs text-slate-500 font-medium mt-1.5"
                  >
                    0 detections
                  </div>
                </div>

                <div class="flex flex-col gap-2">
                  <button @click="startTaskOnImage(img.guid)" class="px-3 py-1.5 bg-blue-600 text-white rounded text-xs font-semibold hover:bg-blue-700 transition">
                    Start Task
                  </button>
                </div>
                
                <div>
                  <p class="text-xs text-slate-500"><span class="font-semibold">GUID:</span> {{ img.guid }}</p>
                  <p class="text-xs text-slate-500 mt-1"><span class="font-semibold">Group ID:</span> {{ img.upload_group_id }}</p>
                  <p class="text-xs text-slate-500 mt-1"><span class="font-semibold">Uploaded At:</span> {{ img.uploaded_at ? new Date(img.uploaded_at).toLocaleString() : '--' }}</p>
                </div>
              </div>

              <!-- Associated Tasks List with Status, Count, and Refresh Button -->
              <div class="space-y-2">
                <div class="flex justify-between items-center">
                  <h4 class="text-xs font-bold uppercase tracking-wider text-slate-500">Associated Tasks</h4>
                  <button 
                    @click="fetchTasksForImage(img.guid)" 
                    class="text-[11px] font-semibold text-blue-600 hover:text-blue-800 bg-blue-50 px-2 py-1 rounded transition border border-blue-100 flex items-center gap-1"
                  >
                    🔄 Refresh Tasks
                  </button>
                </div>

                <div v-if="!imageDetails[img.guid] || imageDetails[img.guid].length === 0" class="text-xs text-slate-400 italic">
                  No tasks associated with this image yet.
                </div>
                <ul v-else class="space-y-1.5">
                  <li 
                    v-for="task in imageDetails[img.guid]" 
                    :key="task.guid" 
                    @click="selectTaskAndFetchDetections(img.guid, task)"
                    :class="[
                      'text-xs font-mono px-3 py-2 rounded cursor-pointer transition flex justify-between items-center',
                      activeTaskId[img.guid] === task.guid ? 'bg-blue-100 text-blue-900 font-bold border border-blue-300' : 'text-slate-700 bg-slate-50 hover:bg-slate-100 border border-slate-200'
                    ]"
                  >
                    <span>{{ task.guid }}</span>
                    <div class="flex gap-2 items-center">
                      <span class="px-1.5 py-0.5 bg-white rounded text-[10px] border border-slate-300 font-sans">
                        Status: {{ task.task_status }}
                      </span>
                      <span class="px-1.5 py-0.5 bg-slate-200 rounded text-[10px] font-sans">
                        Detections: {{ task.detection_count }}
                      </span>
                    </div>
                  </li>
                </ul>
              </div>
            </div>

          </div>
        </div>
      </section>

    </div>
  </main>
</template>